"""
Mapa de categorias → Amazon productType + atributos fixos por categoria.

Espelha os "valores fixos" do template NOGORA (core/config.py
`valores_fixos_padrao`), porém com os NOMES e ENUMS exigidos pela SP-API.
Assim, o fluxo "criar produto novo por SKU" preenche automaticamente os
atributos de conformidade/logística que a Amazon exige por categoria — os
mesmos que o operador já preenche no NOGORA (país de origem, garantia,
baterias=Não, hazmat, certificação, etc.).

Os atributos VARIÁVEIS (título, descrição, bullets, marca, EAN, dimensões,
preço) vêm dos sistemas já integrados (AgentedeTitulos / BDAmazon / Precificação)
e são montados em amazon_listings.criar_produto_por_sku.
"""

from __future__ import annotations

from typing import Any, Optional

from . import amazon_sp_client as sp


# Categoria da UI (mesmas chaves do <select> de sku.html) -> productType Amazon.
PRODUCT_TYPE: dict[str, str] = {
    "padrao": "AUDIO_OR_VIDEO",       # Criar Padrão (a maioria dos produtos)
    "brinquedos": "TOYS_AND_GAMES",
    "potes": "HOME",                  # Potes de Vidro (genérico HOME)
    "suplementos": "NUTRITIONAL_SUPPLEMENT",
}

# Browse node recomendado (obrigatório p/ saúde/suplementos no marketplace BR).
# Para AUDIO/TOYS/HOME a SP-API NÃO exige recommended_browse_nodes na raiz.
# O node de eletrônicos vem do NOGORA ("Eletrônicos e Tecnologia (16209063011)").
BROWSE_NODE: dict[str, Optional[str]] = {
    "padrao": "16209063011",
    "brinquedos": None,
    "potes": None,
    "suplementos": None,  # TODO: preencher o browse node de suplementos do BR
}

# Valores fixos de conformidade do NOGORA, já convertidos p/ os enums da SP-API:
#   NOGORA "País de origem"="Brasil"          -> country_of_origin="BR"
#   NOGORA "Regulamentações..."="Não aplicável"-> supplier_declared_dg_hz_regulation="not_applicable"
#   NOGORA "Baterias são necessárias?"="Não"   -> batteries_required/included=False
#   NOGORA "Descrição da garantia"="90 Dias", "Fonte de energia"="Não aplicável", etc.
_NOGORA_DEFAULTS = {
    "country_of_origin": "BR",
    "supplier_declared_dg_hz_regulation": "not_applicable",
    "number_of_items": 1,
    "power_source_type": "Não aplicável",
    "included_components": "1",
    "warranty_description": "90 Dias",
    "external_testing_certification": "INMETRO: 0000; ANATEL: 0000; Não aplicável",
    "batteries_required": False,
    "batteries_included": False,
}


def product_type(categoria: str) -> str:
    """productType Amazon da categoria (default AUDIO_OR_VIDEO se desconhecida)."""
    return PRODUCT_TYPE.get((categoria or "").strip().lower(), "AUDIO_OR_VIDEO")


def atributos_fixos(categoria: str) -> dict[str, Any]:
    """Atributos fixos (formato SP-API) para a categoria — os defaults do NOGORA
    + browse node quando exigido."""
    mp = sp.marketplace_id()

    def attr(valor: Any) -> list[dict]:
        return [{"value": valor, "marketplace_id": mp}]

    fixos = {chave: attr(valor) for chave, valor in _NOGORA_DEFAULTS.items()}

    node = BROWSE_NODE.get((categoria or "").strip().lower())
    if node:
        fixos["recommended_browse_nodes"] = attr(node)
    return fixos
