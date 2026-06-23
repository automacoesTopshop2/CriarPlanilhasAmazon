# ==============================================================================
# CARREGADOR DE NCM (Modalidade FULL)
# ==============================================================================
# Carrega o código NCM (Classificação fiscal) a partir da planilha de estoque
# Drop ("Drop estoque"), exportada do Tiny.
#
# Regras (definidas pelo negócio):
#   - A chave de busca é o SKU RAIZ (coluna "Código (SKU)"), comparado após
#     remover o prefixo de conta (tratar_sku), igual ao carregador de preços.
#   - O NCM vem da coluna "Classificação fiscal". Na Drop-estoque ele tem
#     pontos (ex.: "8544.42.00"); na Amazon vai SEM pontos (ex.: "85444200").
#   - Os nomes das colunas são localizados por cabeçalho (robusto a mudança de
#     posição), com fallback para as posições conhecidas (B = SKU, E = NCM).
# ==============================================================================

import os
import openpyxl
from typing import Dict, Optional, List
from datetime import datetime

from ..utils import Utilitarios
from ..config import Configuracoes


class CarregadorNCM:
    """
    Carrega e indexa os NCMs da planilha Drop-estoque por SKU raiz.

    Attributes:
        config: Instância de Configuracoes
        dados: Dicionário {sku_base: ncm_sem_pontos}
    """

    # Nomes possíveis dos cabeçalhos (normalizados na comparação)
    NOMES_COLUNA_SKU: List[str] = ['Código (SKU)', 'Codigo (SKU)', 'SKU', 'Código', 'Codigo']
    NOMES_COLUNA_NCM: List[str] = ['Classificação fiscal', 'Classificacao fiscal',
                                   'Código NCM', 'NCM', 'Classificação Fiscal']

    # Fallback de posição (1-based) quando não acha pelo cabeçalho:
    # coluna B = SKU, coluna E = Classificação fiscal
    COLUNA_SKU_FALLBACK = 2
    COLUNA_NCM_FALLBACK = 5

    def __init__(self, config: Optional[Configuracoes] = None, *,
                 arquivo: Optional[str] = None,
                 mapa_prefixo: Optional[Dict[str, str]] = None):
        """
        Args:
            config: Configurações do sistema.
            arquivo: Caminho da planilha Drop-estoque (default = config.arquivo_drop_estoque).
            mapa_prefixo: Mapa {prefixo_sku: conta} usado para extrair o SKU raiz
                (default = config.mapa_prefixo_conta_full).
        """
        self.config = config or Configuracoes()
        self._arquivo_override = arquivo
        self._mapa_prefixo_override = mapa_prefixo
        self.dados: Dict[str, str] = {}
        self._carregado: bool = False
        self._data_carregamento: Optional[datetime] = None
        self._erros: List[str] = []

    @property
    def _arquivo(self) -> str:
        return self._arquivo_override or self.config.arquivo_drop_estoque

    @property
    def _prefixos(self) -> List[str]:
        mapa = self._mapa_prefixo_override or getattr(
            self.config, 'mapa_prefixo_conta_full', self.config.mapa_prefixo_conta
        )
        return list(mapa.keys())

    @property
    def esta_carregado(self) -> bool:
        return self._carregado

    @property
    def quantidade_registros(self) -> int:
        return len(self.dados)

    @property
    def erros(self) -> List[str]:
        return self._erros.copy()

    def arquivo_existe(self) -> bool:
        return os.path.exists(self._arquivo)

    # ------------------------------------------------------------------
    @staticmethod
    def _limpar_ncm(valor) -> Optional[str]:
        """Remove pontos/espaços do NCM. Ex.: '8544.42.00' -> '85444200'."""
        if valor is None:
            return None
        texto = str(valor).strip()
        if not texto:
            return None
        # Tira a parte decimal de floats acidentais (ex.: 85444200.0)
        if texto.endswith('.0'):
            texto = texto[:-2]
        return texto.replace('.', '').replace(' ', '').strip() or None

    def _localizar_colunas(self, planilha) -> tuple:
        """
        Procura a linha de cabeçalho (nas primeiras 15 linhas) que contenha
        as colunas de SKU e NCM. Retorna (linha_cabecalho, idx_sku, idx_ncm)
        com índices 1-based, usando fallback de posição quando necessário.
        """
        alvos_sku = [Utilitarios.normalizar_texto(n) for n in self.NOMES_COLUNA_SKU]
        alvos_ncm = [Utilitarios.normalizar_texto(n) for n in self.NOMES_COLUNA_NCM]

        for linha in range(1, 16):
            idx_sku = idx_ncm = None
            for celula in planilha[linha]:
                if celula.value is None:
                    continue
                nome = Utilitarios.normalizar_texto(str(celula.value))
                col = celula.column if isinstance(celula.column, int) else None
                if col is None:
                    continue
                if idx_sku is None and nome in alvos_sku:
                    idx_sku = col
                if idx_ncm is None and nome in alvos_ncm:
                    idx_ncm = col
            if idx_sku and idx_ncm:
                return linha, idx_sku, idx_ncm

        # Fallback: assume cabeçalho na linha 1 e posições conhecidas (B / E)
        return 1, self.COLUNA_SKU_FALLBACK, self.COLUNA_NCM_FALLBACK

    # ------------------------------------------------------------------
    def carregar(self, forcar_recarga: bool = False) -> bool:
        if self._carregado and not forcar_recarga:
            return True

        self._erros.clear()

        if not self.arquivo_existe():
            self._erros.append(f"Arquivo não encontrado: {self._arquivo}")
            raise FileNotFoundError(
                f"Planilha de NCM (Drop-estoque) não encontrada: {self._arquivo}"
            )

        try:
            workbook = openpyxl.load_workbook(self._arquivo, data_only=True)
            planilha = workbook.active

            linha_cabecalho, idx_sku, idx_ncm = self._localizar_colunas(planilha)
            prefixos = self._prefixos

            self.dados.clear()
            for linha in planilha.iter_rows(min_row=linha_cabecalho + 1,
                                            values_only=True):
                valor_sku = linha[idx_sku - 1] if idx_sku - 1 < len(linha) else None
                valor_ncm = linha[idx_ncm - 1] if idx_ncm - 1 < len(linha) else None
                if not valor_sku:
                    continue
                sku_base = Utilitarios.tratar_sku(valor_sku, prefixos)
                ncm = self._limpar_ncm(valor_ncm)
                if sku_base and ncm:
                    self.dados[sku_base] = ncm

            self._carregado = True
            self._data_carregamento = datetime.now()
            return True

        except Exception as e:
            self._erros.append(f"Erro ao carregar NCM: {str(e)}")
            raise

    def obter_ncm(self, sku_completo: str) -> Optional[str]:
        """Retorna o NCM (sem pontos) para o SKU informado, ou None."""
        if not self._carregado:
            return None
        sku_base = Utilitarios.tratar_sku(sku_completo, self._prefixos)
        if not sku_base:
            return None
        return self.dados.get(sku_base)

    def limpar_cache(self) -> None:
        self.dados.clear()
        self._carregado = False
        self._data_carregamento = None
        self._erros.clear()
