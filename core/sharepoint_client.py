"""
Cliente do Microsoft Graph para baixar arquivos do SharePoint via share-link.

Autenticação: Client Credentials (App-only) via MSAL.
Permissão necessária no Azure AD: Sites.Selected (recomendado) ou Sites.Read.All.

Estratégia: usa o endpoint /shares/{shareId}/driveItem do Graph, que aceita
o link de compartilhamento completo do SharePoint. Não há necessidade de
configurar site_url + path separadamente — o link já contém tudo.

Variáveis de ambiente esperadas:
    SHAREPOINT_TENANT_ID     - ID do tenant Azure AD (UUID)
    SHAREPOINT_CLIENT_ID     - Application (client) ID da App Registration
    SHAREPOINT_CLIENT_SECRET - Client secret da App Registration

Uso:
    cliente = SharePointClient.do_ambiente()
    if cliente:
        info = cliente.testar_url(share_link)            # valida acesso
        bytes_arq = cliente.baixar_por_url(share_link)   # baixa conteúdo
"""

from __future__ import annotations

import base64
import logging
import os
import threading
from typing import Optional, Tuple

import msal
import requests


logger = logging.getLogger(__name__)


_AUTHORITY_BASE = "https://login.microsoftonline.com"
_SCOPE = ["https://graph.microsoft.com/.default"]
_GRAPH_BASE = "https://graph.microsoft.com/v1.0"


class SharePointError(Exception):
    """Erros de integração com SharePoint."""


class SharePointClient:
    """
    Cliente leve do Microsoft Graph para download de arquivos via share-link.

    Thread-safe; pode ser reusado entre requisições. O token é cacheado
    pela própria MSAL e renovado automaticamente.
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

        # validate_authority=False evita lookup de rede no constructor;
        # tenants inválidos retornam erro claro no primeiro acquire_token.
        self._app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"{_AUTHORITY_BASE}/{tenant_id}",
            validate_authority=False,
        )
        self._lock = threading.Lock()

    # ---------------------------------------------------------------------
    # Construtores
    # ---------------------------------------------------------------------
    @classmethod
    def do_ambiente(cls) -> Optional["SharePointClient"]:
        """Cria cliente lendo env vars. Retorna None se faltar credencial."""
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
        with self._lock:
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
    # Encoding de share-link → shareId (formato u!<base64url>)
    # https://learn.microsoft.com/graph/api/shares-get
    # ---------------------------------------------------------------------
    @staticmethod
    def _encode_share_url(share_url: str) -> str:
        if not share_url:
            raise SharePointError("Link vazio.")
        encoded = base64.urlsafe_b64encode(
            share_url.strip().encode("utf-8")
        ).decode("utf-8").rstrip("=")
        return "u!" + encoded

    # ---------------------------------------------------------------------
    # Acesso ao DriveItem por share-link
    # ---------------------------------------------------------------------
    def _driveitem_url(self, share_url: str, sub_path: str = "") -> str:
        share_id = self._encode_share_url(share_url)
        suffix = f"/{sub_path}" if sub_path else ""
        return f"{_GRAPH_BASE}/shares/{share_id}/driveItem{suffix}"

    @staticmethod
    def _erro_http(r: requests.Response, contexto: str) -> SharePointError:
        if r.status_code == 404:
            return SharePointError(
                f"{contexto}: link inválido ou arquivo inacessível (404). "
                f"Verifique se a App está autorizada no site (Sites.Selected)."
            )
        if r.status_code in (401, 403):
            return SharePointError(
                f"{contexto}: sem permissão (HTTP {r.status_code}). "
                f"Para Sites.Selected, peça ao admin do tenant para autorizar a "
                f"App neste site (POST /sites/{{site-id}}/permissions)."
            )
        try:
            r.raise_for_status()
        except requests.exceptions.HTTPError as e:
            return SharePointError(f"{contexto}: HTTP {r.status_code} - {e}")
        return SharePointError(f"{contexto}: status inesperado {r.status_code}")

    def testar_url(self, share_url: str) -> dict:
        """
        Valida o link sem baixar o conteúdo. Retorna metadados do arquivo.

        Útil para o botão "Testar conexão" do painel admin.
        """
        url = self._driveitem_url(share_url)
        r = requests.get(url, headers=self._headers(), timeout=30)
        if not r.ok:
            raise self._erro_http(r, "Validação do link")
        item = r.json()
        return {
            "ok": True,
            "name": item.get("name"),
            "size": item.get("size"),
            "web_url": item.get("webUrl"),
            "last_modified": item.get("lastModifiedDateTime"),
        }

    def baixar_por_url(self, share_url: str) -> bytes:
        """Baixa o conteúdo binário do arquivo apontado pelo share-link."""
        url = self._driveitem_url(share_url, "content")
        r = requests.get(url, headers=self._headers(), timeout=180, allow_redirects=True)
        if not r.ok:
            raise self._erro_http(r, "Download do arquivo")
        return r.content


# =============================================================================
# Helper de alto nível: baixa via share-link e grava no disco
# =============================================================================
def sincronizar_por_url(
    cliente: SharePointClient,
    share_url: str,
    destino_local: str,
) -> Tuple[bool, str]:
    """
    Baixa o arquivo apontado pelo share-link e grava em destino_local.
    Retorna (sucesso, mensagem); não levanta exceção (startup-friendly).
    """
    try:
        conteudo = cliente.baixar_por_url(share_url)
        os.makedirs(os.path.dirname(os.path.abspath(destino_local)) or ".", exist_ok=True)
        with open(destino_local, "wb") as f:
            f.write(conteudo)
        return True, f"Sincronizado: {len(conteudo) // 1024} KB em {destino_local}"
    except SharePointError as e:
        return False, str(e)
    except requests.exceptions.RequestException as e:
        return False, f"Erro de rede: {e}"
    except Exception as e:
        return False, f"Erro inesperado: {e}"
