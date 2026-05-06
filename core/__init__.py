# ==============================================================================
# CORE - Módulo Principal do Sistema de Planilhas Amazon
# ==============================================================================
# Este pacote contém as classes e funções centrais para processamento
# de planilhas da Amazon.
#
# Estrutura:
#   - config.py      : Configurações globais e constantes
#   - utils.py       : Funções utilitárias gerais
#   - carregadores/  : Classes para carregar dados (preços, descrições)
#   - processadores/ : Classes para processar templates (SKU, ASIN, Limpeza)
#   - mapeadores/    : Classes para mapeamento de colunas
# ==============================================================================

from .config import Configuracoes
from .utils import Utilitarios

__all__ = ['Configuracoes', 'Utilitarios']
