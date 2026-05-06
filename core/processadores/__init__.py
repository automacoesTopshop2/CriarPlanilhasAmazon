# ==============================================================================
# PROCESSADORES - Módulo de Processamento de Templates
# ==============================================================================
# Este pacote contém as classes responsáveis por processar templates
# de planilhas Amazon.
#
# Classes:
#   - ProcessadorBase: Classe abstrata base para todos os processadores
#   - ProcessadorSKU: Processamento via lista de SKUs
#   - ProcessadorASIN: Processamento via lista de ASINs
#   - ProcessadorLimpeza: Limpeza de textos em planilhas
# ==============================================================================

from .base import ProcessadorBase
from .sku import ProcessadorSKU
from .asin import ProcessadorASIN
from .limpeza import ProcessadorLimpeza

__all__ = [
    'ProcessadorBase',
    'ProcessadorSKU',
    'ProcessadorASIN',
    'ProcessadorLimpeza'
]
