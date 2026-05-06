"""
Cliente do Microsoft Graph para baixar arquivos do SharePoint.

Autenticação: Client Credentials (App-only) via MSAL.
Permissão necessária: Sites.Selected (mais seguro) ou Sites.Read.All.

Variáveis de ambiente esperadas:
    SHAREPOINT_TENANT_ID   - ID do tenant Azure AD (UUID)
    SHAREPOINT_CLIENT_ID   - Application (client) ID da App Registration
    SHAREPOINT_CLIENT_SECRET - Client secret da App Registration

Uso:
    cliente = SharePointClient.do_ambiente()
    if cliente:
        bytes_arq = cliente.baixar_arquivo(site_url, arquivo_path)

Campos esperados:
    site_url: URL completa do site, ex:
        "https://contoso.sharepoint.com/sites/CriacaoAnuncios"
    arquivo_path: caminho relativo dentro da biblioteca padrão, ex:
        "Documentos Compartilhados/Precificacao Amazon.xlsx"
        ou já com prefixo da biblioteca:
        "Shared Documents/Precificacao Amazon.xlsx"
"""

from __future__ import annotations

import logging
import os
import re
import threading
from typing import Optional, Tuple
from urllib.parse import urlparse

import msal
import requests


logger = logging.getLogger(__name__)


# Authority URL do Azure AD
_AUTHORITY_BASE = "https://login.microsoftonline.com"
# Scope para Client Credentials (sempre /.default)
_SCOPE = ["https://graph.microsoft.com/.default"]
# Endpoint base do Graph
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class SharePointError(Exception):
    """Erros de integração com SharePoint."""


class SharePointClient:
    """
    Cliente leve do Microsoft Graph para download de arquivos.

    Thread-safe; um cliente pode ser reusado entre requisições. O token
    é cacheado pela própria MSAL e renovado automaticamente.
    """

    def __init__(self, tenant_id: str, client_id: str, client_secret: str):
        if not (tenant_id and client_id and client_secret):
            raise SharePointError(
                "Credenciais SharePoint ausentes. Configure SHAREPOINT_TENANT_ID, "
                "SHAREPOINT_CLIENT_ID e SHAREPOINT_CLIENT_SECRET no .env."
            )
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret

        # validate_authority=False evita chamada de rede no constructor — a
        # validação acontece naturalmente no primeiro acquire_token_for_client.
        # Tenants inválidos retornam erro claro do Azure AD nesse momento.
        self._app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"{_AUTHORITY_BASE}/{tenant_id}",
            validate_authority=False,
        )
        # Cache de site-id → evita lookup a cada download
        self._site_id_cache: dict[str, str] = {}
        self._cache_lock = threading.Lock()

    # ---------------------------------------------------------------------
    # Construtores
    # ---------------------------------------------------------------------
    @classmethod
    def do_ambiente(cls) -> Optional["SharePointClient"]:
        """
        Cria cliente lendo variáveis de ambiente. Retorna None se alguma
        delas estiver faltando — útil para o startup decidir se sincroniza.
        """
        tenant = os.getenv("SHAREPOINT_TENANT_ID", "").strip()
        client_id = os.getenv("SHAREPOINT_CLIENT_ID", "").strip()
        secret = os.getenv("SHAREPOINT_CLIENT_SECRET", "").strip()
        if not (tenant and client_id and secret):
            return None
        return cls(tenant, client_id, secret)

    # ---------------------------------------------------------------------
    # Token
    # ---------------------------------------------------------------------
    def _obter_token(self) -> str:
        """Token de aplicativo via Client Credentials. MSAL cuida do cache."""
        result = self._app.acquire_token_silent(_SCOPE, account=None)
        if not result:
            result = self._app.acquire_token_for_client(scopes=_SCOPE)
        if "access_token" not in result:
            err = result.get("error_description") or result.get("error") or str(result)
            raise SharePointError(f"Falha ao obter token: {err}")
        return result["access_token"]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._obter_token()}"}

    # ---------------------------------------------------------------------
    # Resolução de site_id a partir do site_url
    # ---------------------------------------------------------------------
    @staticmethod
    def _parse_site_url(site_url: str) -> Tuple[str, str]:
        """
        Extrai (hostname, server_relative_path) de um site_url.

        Exemplos:
            "https://contoso.sharepoint.com/sites/MyTeam"
                → ("contoso.sharepoint.com", "/sites/MyTeam")
            "https://contoso.sharepoint.com/teams/Outro"
                → ("contoso.sharepoint.com", "/teams/Outro")
            "https://contoso.sharepoint.com"
                → ("contoso.sharepoint.com", "/")  (root site)
        """
        if not site_url:
            raise SharePointError("site_url vazio.")
        u = urlparse(site_url.strip())
        if not u.hostname:
            raise SharePointError(f"site_url inválido: {site_url}")
        path = u.path or "/"
        # Remove barra final
        if path != "/" and path.endswith("/"):
            path = path[:-1]
        return u.hostname, path

    def _obter_site_id(self, site_url: str) -> str:
        """
        Resolve site_url → site_id via Graph API.
        Cacheia o resultado em memória (raramente muda).
        """
        chave = site_url.lower().strip()
        with self._cache_lock:
            cached = self._site_id_cache.get(chave)
        if cached:
            return cached

        host, path = self._parse_site_url(site_url)
        # GET /sites/{host}:{server-relative-path}
        if path == "/":
            url = f"{_GRAPH_BASE}/sites/{host}"
        else:
            url = f"{_GRAPH_BASE}/sites/{host}:{path}"

        r = requests.get(url, headers=self._headers(), timeout=30)
        if r.status_code == 404:
            raise SharePointError(
                f"Site não encontrado: {site_url}. Verifique a URL e se a "
                f"App está autorizada (Sites.Selected exige consent por site)."
            )
        if r.status_code in (401, 403):
            raise SharePointError(
                f"Sem permissão para o site (HTTP {r.status_code}). "
                f"Para Sites.Selected, peça ao admin do tenant para autorizar a "
                f"App neste site."
            )
        r.raise_for_status()
        data = r.json()
        site_id = data.get("id")
        if not site_id:
            raise SharePointError(f"Resposta sem 'id': {data}")

        with self._cache_lock:
            self._site_id_cache[chave] = site_id
        return site_id

    # ---------------------------------------------------------------------
    # Download de arquivo
    # ---------------------------------------------------------------------
    def baixar_arquivo(self, site_url: str, arquivo_path: str) -> bytes:
        """
        Baixa um arquivo de um site SharePoint.

        Args:
            site_url: URL completa do site
            arquivo_path: caminho relativo dentro da biblioteca padrão.
                Exemplos:
                    "Precificacao Amazon.xlsx"  (na raiz da biblioteca)
                    "Pasta/Subpasta/arquivo.xlsx"
                    "Shared Documents/Precificacao Amazon.xlsx"
                A barra inicial (se houver) é removida.

        Retorna os bytes do arquivo.
        """
        if not arquivo_path:
            raise SharePointError("arquivo_path vazio.")
        path = arquivo_path.strip().lstrip("/")
        # SharePoint usa barras (/) — normaliza barras invertidas vindas do Windows
        path = path.replace("\\", "/")
        # Encoding de espaços e caracteres especiais é feito pelo requests via params? Não:
        # neste endpoint usamos a URL literal com path embutido. Mas o requests não codifica
        # automaticamente '#' e '?' no path. Usamos requote para evitar problemas:
        from urllib.parse import quote
        path_encoded = quote(path, safe="/()")

        site_id = self._obter_site_id(site_url)
        url = f"{_GRAPH_BASE}/sites/{site_id}/drive/root:/{path_encoded}:/content"

        r = requests.get(url, headers=self._headers(), timeout=120, stream=True)
        if r.status_code == 404:
            raise SharePointError(
                f"Arquivo não encontrado no site: {arquivo_path}. "
                f"Verifique o caminho (relativo à biblioteca padrão)."
            )
        if r.status_code in (401, 403):
            raise SharePointError(
                f"Sem permissão para baixar (HTTP {r.status_code})."
            )
        r.raise_for_status()
        return r.content

    def testar_conexao(self, site_url: str) -> dict:
        """
        Faz uma chamada leve para validar credenciais + acesso ao site.
        Retorna {ok, site_name, site_id, web_url} ou levanta SharePointError.
        """
        host, path = self._parse_site_url(site_url)
        if path == "/":
            url = f"{_GRAPH_BASE}/sites/{host}"
        else:
            url = f"{_GRAPH_BASE}/sites/{host}:{path}"
        r = requests.get(url, headers=self._headers(), timeout=30)
        if r.status_code == 404:
            raise SharePointError("Site não encontrado.")
        if r.status_code in (401, 403):
            raise SharePointError(
                "Sem permissão. Para Sites.Selected, autorize a App neste site."
            )
        r.raise_for_status()
        data = r.json()
        return {
            "ok": True,
            "site_name": data.get("displayName") or data.get("name"),
            "site_id": data.get("id"),
            "web_url": data.get("webUrl"),
        }


# =============================================================================
# Helper de alto nível: sincroniza um arquivo do SharePoint para o disco
# =============================================================================
def sincronizar_arquivo(
    cliente: SharePointClient,
    site_url: str,
    arquivo_path: str,
    destino_local: str,
) -> Tuple[bool, str]:
    """
    Baixa o arquivo e grava no path local. Retorna (sucesso, mensagem).

    Não levanta exceção — devolve (False, mensagem) em qualquer falha,
    para que o startup do servidor possa logar e continuar.
    """
    try:
        conteudo = cliente.baixar_arquivo(site_url, arquivo_path)
        os.makedirs(os.path.dirname(os.path.abspath(destino_local)) or ".", exist_ok=True)
        with open(destino_local, "wb") as f:
            f.write(conteudo)
        tamanho_kb = len(conteudo) // 1024
        return True, f"Sincronizado: {tamanho_kb} KB em {destino_local}"
    except SharePointError as e:
        return False, str(e)
    except requests.exceptions.RequestException as e:
        return False, f"Erro de rede: {e}"
    except Exception as e:
        return False, f"Erro inesperado: {e}"
