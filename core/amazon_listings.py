"""
Criação de anúncios na Amazon via SP-API (Listings Items 2021-08-01).

Dois fluxos, espelhando os modos do sistema:
    - criar_oferta_por_asin(...)  -> oferta sobre um ASIN JÁ existente no catálogo
      (requirements=LISTING_OFFER_ONLY). Precisa de pouca coisa: SKU, ASIN, preço,
      quantidade, condição e o productType do item.
    - criar_produto_por_sku(...)  -> produto NOVO (ainda não catalogado)
      (requirements=LISTING). Monta os atributos a partir dos dados que já temos
      (título, descrição, bullets, marca, EAN, dimensões) + preço + SKU + tipo.

SEGURANÇA: por padrão usa `mode="VALIDATION_PREVIEW"` — a Amazon valida o payload
e devolve os erros SEM publicar nada. Para publicar de verdade, passe
`mode=None` explicitamente.

Os nomes de atributos (item_name, brand, bullet_point, ...) seguem o schema dos
product types da Amazon; o conjunto EXATO de obrigatórios varia por tipo. Use o
modo de validação + `amazon_sp_client.definicoes_tipo_produto(tipo)` para ajustar
por categoria. `atributos_extra` permite sobrescrever/complementar qualquer campo.
"""

from __future__ import annotations

from typing import Any, Optional

from . import amazon_sp_client as sp
from . import amazon_categorias


def _mp() -> str:
    return sp.marketplace_id()


def _attr(value: Any) -> list[dict]:
    """Atributo simples no formato Amazon: [{value, marketplace_id}]."""
    return [{"value": value, "marketplace_id": _mp()}]


def _num(valor: Any) -> Optional[float]:
    if valor is None:
        return None
    s = str(valor).strip().replace(",", ".")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _purchasable_offer(preco: float, *, moeda: str = "BRL") -> list[dict]:
    return [{
        "currency": moeda,
        "marketplace_id": _mp(),
        "our_price": [{"schedule": [{"value_with_tax": round(float(preco), 2)}]}],
    }]


def _fulfillment(quantidade: int) -> list[dict]:
    return [{"fulfillment_channel_code": "DEFAULT", "quantity": int(quantidade)}]


# --------------------------------------------------------------------------- #
# Fluxo 1 — oferta sobre ASIN já existente
# --------------------------------------------------------------------------- #
def criar_oferta_por_asin(
    *,
    sku: str,
    asin: str,
    preco: float,
    quantidade: int = 1,
    condicao: str = "new_new",
    product_type: Optional[str] = None,
    atributos_extra: Optional[dict] = None,
    mode: Optional[str] = "VALIDATION_PREVIEW",
) -> dict:
    """Cria/valida uma oferta para um ASIN existente.

    Se `product_type` não vier, é descoberto via Catalog Items (summaries).
    Devolve a resposta da SP-API (com `issues`/`status`).
    """
    asin = (asin or "").strip()
    if not asin:
        raise sp.AmazonSPError("asin é obrigatório para criar oferta por ASIN.")

    if not product_type:
        item = sp.buscar_catalogo_por_asin(asin)
        if not item:
            raise sp.AmazonSPError(f"ASIN {asin} não encontrado no marketplace.")
        summaries = item.get("summaries") or []
        product_type = (summaries[0].get("productType") if summaries else None) or "PRODUCT"

    attrs: dict[str, Any] = {
        "condition_type": _attr(condicao),
        "merchant_suggested_asin": _attr(asin),
        "purchasable_offer": _purchasable_offer(preco),
        "fulfillment_availability": _fulfillment(quantidade),
    }
    if atributos_extra:
        attrs.update(atributos_extra)

    body = {
        "productType": product_type,
        "requirements": "LISTING_OFFER_ONLY",
        "attributes": attrs,
    }
    return sp.put_listing(sku, body, mode=mode)


# --------------------------------------------------------------------------- #
# Fluxo 2 — produto novo (ainda não catalogado)
# --------------------------------------------------------------------------- #
def criar_produto_por_sku(
    *,
    sku: str,
    product_type: Optional[str] = None,
    categoria: Optional[str] = None,
    titulo: str,
    descricao: str = "",
    bullets: Optional[list[str]] = None,
    marca: str = "",
    ean: str = "",
    preco: Optional[float] = None,
    quantidade: int = 1,
    condicao: str = "new_new",
    peso_kg: Any = None,
    comprimento_cm: Any = None,
    largura_cm: Any = None,
    altura_cm: Any = None,
    imagem_principal_url: str = "",
    atributos_extra: Optional[dict] = None,
    mode: Optional[str] = "VALIDATION_PREVIEW",
) -> dict:
    """Cria/valida um PRODUTO NOVO + oferta a partir dos dados que já temos.

    Informe `categoria` (padrao/brinquedos/potes/suplementos) — daí o
    `product_type` e os atributos fixos de conformidade (país de origem, baterias,
    garantia, hazmat, etc.) saem do mapa `amazon_categorias` (espelha o NOGORA).
    Alternativamente passe `product_type` direto. `atributos_extra` sobrescreve
    qualquer atributo. Rode em VALIDATION_PREVIEW e ajuste conforme os `issues`.
    """
    if categoria and not product_type:
        product_type = amazon_categorias.product_type(categoria)
    if not product_type:
        raise sp.AmazonSPError("Informe `categoria` ou `product_type` para criar produto novo.")
    if not titulo:
        raise sp.AmazonSPError("titulo é obrigatório para criar produto novo.")

    attrs: dict[str, Any] = {}
    # 1) Atributos fixos de conformidade da categoria (defaults do NOGORA).
    if categoria:
        attrs.update(amazon_categorias.atributos_fixos(categoria))
    # 2) Atributos do produto (variáveis).
    attrs["item_name"] = _attr(titulo)
    attrs["condition_type"] = _attr(condicao)
    if marca:
        attrs["brand"] = _attr(marca)
        attrs["manufacturer"] = _attr(marca)
    if descricao:
        attrs["product_description"] = _attr(descricao)
    if bullets:
        attrs["bullet_point"] = [{"value": b, "marketplace_id": _mp()}
                                 for b in bullets if str(b).strip()][:5]
    if ean:
        attrs["externally_assigned_product_identifier"] = [
            {"type": "ean", "value": str(ean).strip(), "marketplace_id": _mp()}
        ]

    # Dimensões (cm) e peso (kg) — formato comum; pode variar por product type.
    peso = _num(peso_kg)
    if peso is not None:
        attrs["item_package_weight"] = [
            {"unit": "kilograms", "value": peso, "marketplace_id": _mp()}
        ]
    dims = {
        "length": _num(comprimento_cm),
        "width": _num(largura_cm),
        "height": _num(altura_cm),
    }
    if any(v is not None for v in dims.values()):
        pacote: dict[str, Any] = {"marketplace_id": _mp()}
        for chave, valor in dims.items():
            if valor is not None:
                pacote[chave] = {"unit": "centimeters", "value": valor}
        attrs["item_package_dimensions"] = [pacote]

    if imagem_principal_url:
        attrs["main_product_image_locator"] = [
            {"media_location": imagem_principal_url, "marketplace_id": _mp()}
        ]

    # Oferta (preço + estoque) — opcional; sem preço gera só o produto.
    if preco is not None:
        attrs["purchasable_offer"] = _purchasable_offer(preco)
        attrs["fulfillment_availability"] = _fulfillment(quantidade)

    if atributos_extra:
        attrs.update(atributos_extra)

    body = {
        "productType": product_type,
        "requirements": "LISTING" if preco is not None else "LISTING_PRODUCT_ONLY",
        "attributes": attrs,
    }
    return sp.put_listing(sku, body, mode=mode)


def asins_ja_listados(asins: list[str]) -> dict[str, list[str]]:
    """Mapa {asin: [skus]} dos ASINs que JÁ têm anúncio do seller na conta.

    Agrupa em lotes de 20 (limite do searchListingsItems) e consulta a SP-API.
    ASINs sem anúncio simplesmente não aparecem no resultado. Erros de uma
    chamada não derrubam as demais (o ASIN fica como "não verificado" → ausente).
    """
    limpos: list[str] = []
    vistos: set[str] = set()
    for a in asins:
        a = (a or "").strip()
        if a and a not in vistos:
            vistos.add(a)
            limpos.append(a)

    encontrados: dict[str, list[str]] = {}
    for i in range(0, len(limpos), 20):
        lote = limpos[i:i + 20]
        try:
            resp = sp.buscar_listings(lote, tipo="ASIN")
        except sp.AmazonSPError:
            continue
        for item in (resp.get("items") or []):
            sku = item.get("sku") or ""
            for s in (item.get("summaries") or []):
                asin = (s.get("asin") or "").strip()
                if asin:
                    encontrados.setdefault(asin, [])
                    if sku and sku not in encontrados[asin]:
                        encontrados[asin].append(sku)
    return encontrados


def resumo_issues(resposta: dict) -> dict:
    """Extrai um resumo amigável da resposta do put_listing."""
    issues = resposta.get("issues") or []
    erros = [i for i in issues if i.get("severity") == "ERROR"]
    avisos = [i for i in issues if i.get("severity") == "WARNING"]
    return {
        "status": resposta.get("status"),
        "sku": resposta.get("sku"),
        "submission_id": resposta.get("submissionId"),
        "total_erros": len(erros),
        "total_avisos": len(avisos),
        "erros": [f"{i.get('code')}: {i.get('message')}" for i in erros],
        "avisos": [f"{i.get('code')}: {i.get('message')}" for i in avisos],
    }
