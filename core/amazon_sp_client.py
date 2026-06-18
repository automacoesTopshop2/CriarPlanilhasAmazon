"""
Cliente da Amazon Selling Partner API (SP-API) — criação de anúncios.

Autenticação: LWA (Login with Amazon). NÃO usa mais AWS SigV4 — basta o
access token (header `x-amz-access-token`). O access token (1h) é obtido com
`grant_type=refresh_token` em https://api.amazon.com/auth/o2/token usando
client_id + client_secret + refresh_token.

Credenciais (env):
    AMAZON_LWA_CLIENT_ID      -> "amzn1.application-oa2-client...."
    AMAZON_LWA_CLIENT_SECRET  -> "amzn1.oa2-cs.v1...."
    AMAZON_SP_REFRESH_TOKEN   -> "Atzr|..."  (obtido na auto-autorização do app)
    AMAZON_SELLER_ID          -> merchant/seller token (ex.: "A1B2C3...")
    AMAZON_MARKETPLACE_ID     -> default Brasil "A2Q3Y263D1MK6M"
    AMAZON_SP_ENDPOINT        -> default NA "https://sellingpartnerapi-na.amazon.com"
                                 (Brasil roda na região da América do Norte)

Operações expostas:
    - buscar_catalogo_por_asin(asin)   GET  /catalog/2022-04-01/items/{asin}
    - restricoes_listagem(asin, cond)  GET  /listings/2021-08-01/restrictions
    - definicoes_tipo_produto(tipo)    GET  /definitions/2020-09-01/productTypes/{tipo}
    - participacoes()                  GET  /sellers/v1/marketplaceParticipations
    - put_listing(sku, body, mode)     PUT  /listings/2021-08-01/items/{sellerId}/{sku}

Fontes (SP-API docs):
  https://developer-docs.amazon.com/sp-api/docs/connecting-to-the-selling-partner-api
  https://developer-docs.amazon.com/sp-api/docs/listings-items-api
  https://developer-docs.amazon.com/sp-api/docs/preview-errors-before-creating-a-listing
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
DEFAULT_ENDPOINT = "https://sellingpartnerapi-na.amazon.com"  # região NA (inclui Brasil)
DEFAULT_MARKETPLACE_ID = "A2Q3Y263D1MK6M"  # Amazon.com.br
TIMEOUT_PADRAO = 30


class AmazonSPError(Exception):
    """Erro genérico ao falar com a SP-API."""

    def __init__(self, mensagem: str, *, status: Optional[int] = None, corpo: Any = None):
        super().__init__(mensagem)
        self.status = status
        self.corpo = corpo


class AmazonSPAuthError(AmazonSPError):
    """Falha de autenticação LWA (client/secret/refresh token inválidos)."""


class AmazonSPConfigError(AmazonSPError):
    """Credencial obrigatória ausente no ambiente."""


# --------------------------------------------------------------------------- #
# Configuração (lida do ambiente)
# --------------------------------------------------------------------------- #
def _env(nome: str, *, obrigatorio: bool = True, default: str = "") -> str:
    valor = (os.getenv(nome) or default).strip()
    if obrigatorio and not valor:
        raise AmazonSPConfigError(
            f"{nome} não está configurada no ambiente. Defina as credenciais "
            "da SP-API (ver core/amazon_sp_client.py)."
        )
    return valor


def endpoint() -> str:
    return (os.getenv("AMAZON_SP_ENDPOINT") or DEFAULT_ENDPOINT).rstrip("/")


def marketplace_id() -> str:
    return (os.getenv("AMAZON_MARKETPLACE_ID") or DEFAULT_MARKETPLACE_ID).strip()


def seller_id() -> str:
    return _env("AMAZON_SELLER_ID")


def credenciais_ok() -> bool:
    """True se as credenciais mínimas para autenticar estão presentes."""
    return all(
        (os.getenv(n) or "").strip()
        for n in ("AMAZON_LWA_CLIENT_ID", "AMAZON_LWA_CLIENT_SECRET", "AMAZON_SP_REFRESH_TOKEN")
    )


# --------------------------------------------------------------------------- #
# LWA access token (cacheado em memória até ~60s antes de expirar)
# --------------------------------------------------------------------------- #
_token_cache: dict[str, Any] = {"valor": None, "expira_em": 0.0}


def _access_token(forcar: bool = False) -> str:
    agora = time.monotonic()
    if not forcar and _token_cache["valor"] and agora < _token_cache["expira_em"]:
        return _token_cache["valor"]

    dados = {
        "grant_type": "refresh_token",
        "refresh_token": _env("AMAZON_SP_REFRESH_TOKEN"),
        "client_id": _env("AMAZON_LWA_CLIENT_ID"),
        "client_secret": _env("AMAZON_LWA_CLIENT_SECRET"),
    }
    try:
        resp = requests.post(
            LWA_TOKEN_URL,
            data=dados,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            timeout=TIMEOUT_PADRAO,
        )
    except requests.RequestException as e:
        raise AmazonSPError(f"Falha de rede ao obter token LWA: {e}") from e

    if resp.status_code in (400, 401):
        raise AmazonSPAuthError(
            f"LWA recusou a autenticação ({resp.status_code}): {resp.text[:300]}",
            status=resp.status_code,
        )
    if not resp.ok:
        raise AmazonSPError(f"LWA HTTP {resp.status_code}: {resp.text[:300]}", status=resp.status_code)

    try:
        corpo = resp.json()
    except ValueError as e:
        raise AmazonSPError(f"Resposta LWA não-JSON: {resp.text[:200]}") from e

    token = corpo.get("access_token")
    if not token:
        raise AmazonSPAuthError(f"LWA não devolveu access_token: {corpo}")
    expires_in = int(corpo.get("expires_in") or 3600)
    _token_cache["valor"] = token
    _token_cache["expira_em"] = agora + max(60, expires_in - 60)
    return token


# --------------------------------------------------------------------------- #
# Request genérico à SP-API
# --------------------------------------------------------------------------- #
def _request(method: str, path: str, *, params: Optional[dict] = None,
             json_body: Optional[dict] = None) -> dict:
    url = f"{endpoint()}{path}"
    headers = {
        "x-amz-access-token": _access_token(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.request(method, url, headers=headers, params=params,
                                json=json_body, timeout=TIMEOUT_PADRAO)
    except requests.RequestException as e:
        raise AmazonSPError(f"Falha de rede ao chamar {url}: {e}") from e

    if resp.status_code in (401, 403):
        # Token pode ter expirado/contexto inválido — uma tentativa de renovar.
        try:
            headers["x-amz-access-token"] = _access_token(forcar=True)
            resp = requests.request(method, url, headers=headers, params=params,
                                    json=json_body, timeout=TIMEOUT_PADRAO)
        except requests.RequestException as e:
            raise AmazonSPError(f"Falha de rede ao chamar {url}: {e}") from e
        if resp.status_code in (401, 403):
            raise AmazonSPAuthError(
                f"SP-API recusou ({resp.status_code}): {resp.text[:300]}",
                status=resp.status_code, corpo=_corpo(resp),
            )

    if not resp.ok:
        raise AmazonSPError(
            f"SP-API HTTP {resp.status_code} em {method} {path}: {resp.text[:400]}",
            status=resp.status_code, corpo=_corpo(resp),
        )
    return _corpo(resp)


def _corpo(resp: requests.Response) -> dict:
    try:
        return resp.json()
    except ValueError:
        return {"_raw": resp.text}


# --------------------------------------------------------------------------- #
# Operações de catálogo / restrições / definições
# --------------------------------------------------------------------------- #
def buscar_catalogo_por_asin(asin: str, *, included: str = "summaries,productTypes") -> Optional[dict]:
    """GET /catalog/2022-04-01/items/{asin}. None se 404 (ASIN não existe no MP)."""
    try:
        return _request(
            "GET", f"/catalog/2022-04-01/items/{quote(asin, safe='')}",
            params={"marketplaceIds": marketplace_id(), "includedData": included},
        )
    except AmazonSPError as e:
        if e.status == 404:
            return None
        raise


def restricoes_listagem(asin: str, *, condition: str = "new_new") -> dict:
    """GET /listings/2021-08-01/restrictions — checa se o seller pode listar o ASIN."""
    return _request(
        "GET", "/listings/2021-08-01/restrictions",
        params={
            "asin": asin,
            "conditionType": condition,
            "sellerId": seller_id(),
            "marketplaceIds": marketplace_id(),
        },
    )


def definicoes_tipo_produto(tipo: str, *, requirements: str = "LISTING") -> dict:
    """GET /definitions/2020-09-01/productTypes/{tipo} — schema de atributos do tipo."""
    return _request(
        "GET", f"/definitions/2020-09-01/productTypes/{quote(tipo, safe='')}",
        params={
            "marketplaceIds": marketplace_id(),
            "requirements": requirements,
            "locale": "pt_BR",
        },
    )


def participacoes() -> dict:
    """GET /sellers/v1/marketplaceParticipations — útil para descobrir o sellerId."""
    return _request("GET", "/sellers/v1/marketplaceParticipations")


# --------------------------------------------------------------------------- #
# Criação/validação de anúncio (Listings Items)
# --------------------------------------------------------------------------- #
def put_listing(sku: str, body: dict, *, mode: Optional[str] = "VALIDATION_PREVIEW",
                included_data: str = "issues,status") -> dict:
    """PUT /listings/2021-08-01/items/{sellerId}/{sku}.

    `mode="VALIDATION_PREVIEW"` valida SEM publicar (recomendado para teste).
    Passe `mode=None` para realmente criar/atualizar o anúncio na conta.
    """
    params = {"marketplaceIds": marketplace_id(), "includedData": included_data}
    if mode:
        params["mode"] = mode
    return _request(
        "PUT",
        f"/listings/2021-08-01/items/{quote(seller_id(), safe='')}/{quote(sku, safe='')}",
        params=params,
        json_body=body,
    )
