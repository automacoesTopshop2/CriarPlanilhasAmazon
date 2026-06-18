"""
Cliente HTTP para a API de catálogo do AgentedeTitulos (banco unificado de
títulos/descrições da Amazon).

Base URL: env `TITULOS_API_BASE` (default = produção). Inclui o sufixo `/api`.
Autenticação: header `X-API-Key` com `TITULOS_API_KEY` (chave `tsk_...`).

Usado como fonte alternativa da base de Descrição: em vez de ler a planilha
DESCRIÇÃO.xlsx, consulta `GET /api/catalog/{sku}` e traz título, descrição,
modelo, peso, medidas e marcadores (bullets). Apenas os campos que JÁ vinham da
planilha de descrição — marca/EAN continuam vindo do operador.

Funções públicas:
    - consultar_sku(sku) -> dict | None   (None se 404)
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import quote

import requests

log = logging.getLogger(__name__)

DEFAULT_BASE = "https://frontend-production-3bf7b.up.railway.app/api"
TIMEOUT_PADRAO = 20


class TitulosError(Exception):
    """Erro genérico ao falar com a API de Títulos."""

    def __init__(self, mensagem: str, *, status: Optional[int] = None):
        super().__init__(mensagem)
        self.status = status


class TitulosAuthError(TitulosError):
    """401/403 — chave de API inválida/revogada/sem escopo."""


class TitulosRateLimitError(TitulosError):
    """429 — rate-limit por chave de API."""


def _base() -> str:
    return (os.getenv("TITULOS_API_BASE") or DEFAULT_BASE).rstrip("/")


def _key() -> str:
    chave = (os.getenv("TITULOS_API_KEY") or "").strip()
    if not chave:
        raise TitulosError(
            "TITULOS_API_KEY não está configurada no ambiente. Defina a variável "
            "no Railway (ou .env em dev) com a chave `tsk_...` do AgentedeTitulos."
        )
    return chave


def _headers() -> dict:
    return {"X-API-Key": _key(), "Accept": "application/json"}


def consultar_sku(sku: str) -> Optional[dict]:
    """GET /api/catalog/{sku} — devolve o listing do SKU (dict) ou None se 404.

    O dict traz: titulo_mlb, titulo_amazon, descricao, marcadores[5], modelo_ref,
    ref_asin, ean, marca, categoria, peso, comprimento, largura, altura, etc.
    """
    sku = (sku or "").strip()
    if not sku:
        return None
    url = f"{_base()}/catalog/{quote(sku, safe='')}"
    try:
        resp = requests.get(url, headers=_headers(), timeout=TIMEOUT_PADRAO)
    except requests.RequestException as e:
        raise TitulosError(f"Falha de rede ao consultar {url}: {e}") from e

    if resp.status_code == 404:
        return None
    if resp.status_code in (401, 403):
        raise TitulosAuthError(
            f"API de Títulos recusou a autenticação ({resp.status_code}). "
            "Verifique a TITULOS_API_KEY.",
            status=resp.status_code,
        )
    if resp.status_code == 429:
        raise TitulosRateLimitError(
            "Rate-limit da API de Títulos excedido. Aguarde alguns segundos.",
            status=429,
        )
    if not resp.ok:
        raise TitulosError(
            f"API de Títulos retornou HTTP {resp.status_code}: {resp.text[:200]}",
            status=resp.status_code,
        )
    try:
        data = resp.json()
    except ValueError as e:
        raise TitulosError(
            f"Resposta da API de Títulos não é JSON válido: {resp.text[:200]}"
        ) from e
    return data if isinstance(data, dict) else None
