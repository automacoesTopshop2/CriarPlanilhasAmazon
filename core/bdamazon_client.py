"""
Cliente HTTP para a API REST do BDAmazon.

Documentação do contrato: ver chat / repositório do BDAmazon.
Base URL: configurável via BDAMAZON_API_BASE (default = produção).
Autenticação: header X-API-Key com BDAMAZON_API_KEY.

Funções públicas:
    - listar_contas()          -> list[Conta]
    - criar_sku(...)           -> SkuCriado
    - criar_skus_lote(itens)   -> dict (sucesso parcial: total/criados/falhas/resultados)
    - consultar_sku(sku_market)-> SkuCriado | None
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, List, Optional
from urllib.parse import quote

import requests


log = logging.getLogger(__name__)


DEFAULT_BASE = "https://bdamazon-web-production.up.railway.app/api/v1"
TIMEOUT_PADRAO = 15
# O lote processa até 1000 itens (concorrência interna) — pode demorar bem mais
# que uma criação unitária; damos uma folga generosa de timeout.
TIMEOUT_LOTE = 120


class BDAmazonError(Exception):
    """Erro genérico ao falar com a API BDAmazon."""

    def __init__(self, mensagem: str, *, status: Optional[int] = None,
                 detail: Any = None):
        super().__init__(mensagem)
        self.status = status
        self.detail = detail


class BDAmazonAuthError(BDAmazonError):
    """401/403 — chave inválida/revogada/sem escopo."""


class BDAmazonNotFoundError(BDAmazonError):
    """404 — conta_codigo / usuario_codigo / sku_market não existe."""


class BDAmazonRateLimitError(BDAmazonError):
    """429 — rate-limit por IP."""


@dataclass
class Conta:
    codigo: str
    nome: str
    marca: str
    tipo_canal: str
    prefixo_sku: str

    @classmethod
    def from_dict(cls, d: dict) -> "Conta":
        return cls(
            codigo=d.get("codigo", ""),
            nome=d.get("nome", ""),
            marca=d.get("marca", ""),
            tipo_canal=d.get("tipo_canal", ""),
            prefixo_sku=d.get("prefixo_sku", ""),
        )


# Classificação de sensibilidade do produto no catálogo interno do BDAmazon.
# Devolvida por GET /api/v1/skus/{sku_market} no campo `status_produto`.
STATUS_PRODUTO_VALIDOS = ("LIVRE", "SENSIVEL", "PROIBIDO", "INATIVO")


@dataclass
class SkuCriado:
    sku_market: str
    sku_raiz: str
    versao: int
    conta_codigo: str
    conta_nome: str
    asin: Optional[str]
    titulo: Optional[str]
    aguardando_titulo: bool
    criado_em: str
    criado_por: str
    raw: dict
    # Campos extras devolvidos só pelo GET /skus/{sku_market} (não pelo POST).
    # Ficam None quando vêm da resposta de criação ou se o SKU raiz não consta
    # no catálogo interno.
    ean: Optional[str] = None
    status_produto: Optional[str] = None   # LIVRE | SENSIVEL | PROIBIDO | INATIVO | None
    titulo_produto: Optional[str] = None
    estoque_produto: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict) -> "SkuCriado":
        est = d.get("estoque_produto")
        try:
            estoque = int(est) if est is not None else None
        except (TypeError, ValueError):
            estoque = None
        return cls(
            sku_market=d.get("sku_market", ""),
            sku_raiz=d.get("sku_raiz", ""),
            versao=int(d.get("versao") or 1),
            conta_codigo=d.get("conta_codigo", ""),
            conta_nome=d.get("conta_nome", ""),
            asin=d.get("asin"),
            titulo=d.get("titulo"),
            aguardando_titulo=bool(d.get("aguardando_titulo", False)),
            criado_em=d.get("criado_em", ""),
            criado_por=d.get("criado_por", ""),
            raw=d,
            ean=d.get("ean"),
            status_produto=d.get("status_produto"),
            titulo_produto=d.get("titulo_produto"),
            estoque_produto=estoque,
        )


def _base() -> str:
    return (os.getenv("BDAMAZON_API_BASE") or DEFAULT_BASE).rstrip("/")


def _key() -> str:
    chave = os.getenv("BDAMAZON_API_KEY", "").strip()
    if not chave:
        raise BDAmazonError(
            "BDAMAZON_API_KEY não está configurada no ambiente. "
            "Defina a variável no Railway (ou .env em dev) com a chave "
            "fornecida pelo admin do BDAmazon."
        )
    return chave


def _headers() -> dict:
    return {
        "X-API-Key": _key(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _request(method: str, path: str, *, json_body: Optional[dict] = None,
             timeout: int = TIMEOUT_PADRAO) -> dict:
    url = f"{_base()}{path}"
    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=_headers(),
            json=json_body,
            timeout=timeout,
        )
    except requests.RequestException as e:
        raise BDAmazonError(f"Falha de rede ao chamar {url}: {e}") from e

    if resp.status_code == 401 or resp.status_code == 403:
        detail = _detail(resp)
        raise BDAmazonAuthError(
            f"BDAmazon recusou a autenticação ({resp.status_code}): {detail}",
            status=resp.status_code,
            detail=detail,
        )
    if resp.status_code == 404:
        detail = _detail(resp)
        raise BDAmazonNotFoundError(
            f"Recurso não encontrado no BDAmazon: {detail}",
            status=404,
            detail=detail,
        )
    if resp.status_code == 429:
        raise BDAmazonRateLimitError(
            "Rate-limit do BDAmazon excedido (60 req/min). "
            "Aguarde alguns segundos e tente novamente.",
            status=429,
        )
    if not resp.ok:
        detail = _detail(resp)
        raise BDAmazonError(
            f"BDAmazon retornou HTTP {resp.status_code}: {detail}",
            status=resp.status_code,
            detail=detail,
        )

    try:
        return resp.json()
    except ValueError as e:
        raise BDAmazonError(
            f"Resposta do BDAmazon não é JSON válido: {resp.text[:200]}"
        ) from e


def _detail(resp: requests.Response) -> str:
    try:
        body = resp.json()
        if isinstance(body, dict):
            return str(body.get("detail") or body)
        return str(body)
    except ValueError:
        return resp.text[:200]


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

def listar_contas() -> List[Conta]:
    """GET /api/v1/contas — todas as contas ativas com codigo_externo definido."""
    data = _request("GET", "/contas")
    if not isinstance(data, list):
        raise BDAmazonError(f"Resposta inesperada em /contas: {data!r}")
    return [Conta.from_dict(item) for item in data]


def criar_conta(
    *,
    nome: str,
    marca: str,
    tipo_canal: str,
    prefixo_sku: str,
    codigo_externo: Optional[str] = None,
    observacao: Optional[str] = None,
) -> Conta:
    """POST /api/v1/contas — cria uma conta nova e devolve os dados persistidos.

    `tipo_canal`: BASE | B2B | CLA | FBA | DBA.
    `codigo_externo` é opcional — o servidor deriva do prefixo (sem o "-" final)
    quando ausente. Levanta BDAmazonError em caso de conflito/erro.
    """
    body: dict = {
        "nome": nome,
        "marca": marca,
        "tipo_canal": tipo_canal,
        "prefixo_sku": prefixo_sku,
    }
    if codigo_externo:
        body["codigo_externo"] = codigo_externo
    if observacao:
        body["observacao"] = observacao
    data = _request("POST", "/contas", json_body=body)
    return Conta.from_dict(data)


def criar_sku(
    *,
    conta_codigo: str,
    sku_raiz: str,
    usuario_codigo: str,
    asin: Optional[str] = None,
    titulo: Optional[str] = None,
    tipo_anuncio_id: Optional[int] = None,
    obs: Optional[str] = None,
    data_lancamento: Optional[str] = None,
) -> SkuCriado:
    """POST /api/v1/skus — cria SKU e devolve o sku_market gerado."""
    body: dict = {
        "conta_codigo": conta_codigo,
        "sku_raiz": sku_raiz,
        "usuario_codigo": usuario_codigo,
    }
    if asin:
        body["asin"] = asin
    if titulo:
        body["titulo"] = titulo
    if tipo_anuncio_id is not None:
        body["tipo_anuncio_id"] = tipo_anuncio_id
    if obs:
        body["obs"] = obs
    if data_lancamento:
        body["data_lancamento"] = data_lancamento

    data = _request("POST", "/skus", json_body=body)
    return SkuCriado.from_dict(data)


def criar_skus_lote(itens: List[dict]) -> dict:
    """POST /api/v1/skus/lote — cria vários SKUs numa única chamada.

    `itens`: lista de dicts com `conta_codigo`, `sku_raiz`, `usuario_codigo`
    (obrigatórios) e opcionais (`asin`, `ean`, `titulo`, `tipo_anuncio_id`,
    `obs`, `data_lancamento`).

    Devolve o envelope da API (sucesso parcial):
        {"total", "criados", "falhas", "resultados": [...]}
    onde cada resultado tem `indice` (casando com a ordem de entrada) e
    `ok: true|false`. HTTP 207 (parcial) é tratado como sucesso pelo `_request`
    (status < 400). O teto é 1000 itens/lote (acima → BDAmazonError via 413);
    o rate-limit conta o lote inteiro como 1 requisição.
    """
    data = _request("POST", "/skus/lote", json_body={"itens": itens},
                    timeout=TIMEOUT_LOTE)
    if not isinstance(data, dict) or "resultados" not in data:
        raise BDAmazonError(f"Resposta inesperada em /skus/lote: {data!r}")
    return data


def consultar_sku(sku_market: str) -> Optional[SkuCriado]:
    """GET /api/v1/skus/{sku_market} — None se 404.

    Além dos dados do anúncio, o SkuCriado devolvido carrega a classificação
    de sensibilidade do catálogo interno (`status_produto`: LIVRE/SENSIVEL/
    PROIBIDO/INATIVO/None) e o estoque/título oficiais.
    """
    # quote(safe="") garante que o sku_market vire um único segmento de path
    # (sem permitir '/' ou '..' escaparem para outras rotas da API).
    try:
        data = _request("GET", f"/skus/{quote(sku_market, safe='')}")
    except BDAmazonNotFoundError:
        return None
    return SkuCriado.from_dict(data)
