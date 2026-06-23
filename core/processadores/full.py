# ==============================================================================
# PROCESSADOR FULL
# ==============================================================================
# Modalidade FULL (Logística da Amazon / FBA) usando contas CONTA-CLA.
#
# É uma variante do ProcessadorASIN — mesma entrada (ASIN + SKU) e mesmo
# template/saída (ListaASINS_*.xlsm) —, mas isolada nas divergências do FULL:
#
#   1. PREÇO: vem da aba "CLA" da "Precificacao Amazon - Full.xlsx", usando os
#      prefixos CLA (ex.: BOX-CLA- -> coluna Box2Brasil). Verdal/Tacnar ainda
#      não têm coluna -> preço fica vazio.
#   2. NCM: por linha, vindo da planilha Drop-estoque (sem pontos).
#   3. COLUNAS FIXAS: canal = "Logística da Amazon (AN)", Modelo de Envio =
#      "Modelo padrão da Amazon", Origem da mercadoria = 1, Quantidade = 0
#      (ver config.valores_fixos_full).
# ==============================================================================

from typing import Dict, Any, Optional, Callable
from datetime import datetime

from .asin import ProcessadorASIN
from ..config import Configuracoes
from ..carregadores import CarregadorPrecos, CarregadorNCM


class ProcessadorFULL(ProcessadorASIN):
    """Processador da modalidade FULL (CONTA-CLA + Logística da Amazon)."""

    def __init__(self, config: Optional[Configuracoes] = None):
        super().__init__(config)

        # Base de preços própria: aba CLA + prefixos CLA da Precificação Full.
        self.carregador_precos = CarregadorPrecos(
            self.config,
            arquivo=self.config.arquivo_precificacao_full,
            aba=self.config.aba_precificacao_full,
            mapa_prefixo=self.config.mapa_prefixo_conta_full,
        )

        # Base de NCM (Drop-estoque), indexada pelo SKU raiz.
        self.carregador_ncm = CarregadorNCM(
            self.config,
            arquivo=self.config.arquivo_drop_estoque,
            mapa_prefixo=self.config.mapa_prefixo_conta_full,
        )

    def _obter_nome_arquivo_saida(self) -> str:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M')
        return f"CriacaoFULL_{timestamp}.xlsm"

    def _carregar_bases_dados(self, callback_status: Optional[Callable] = None) -> bool:
        # Preço (FULL) + Descrição/medidas — fatal se ausentes (igual ao base).
        super()._carregar_bases_dados(callback_status)

        # NCM — não-fatal: se a Drop-estoque faltar, segue sem NCM (avisos por linha).
        if callback_status:
            callback_status("📚 Carregando NCM (Drop-estoque)...")
        try:
            self.carregador_ncm.carregar()
        except FileNotFoundError as e:
            self._adicionar_erro("SISTEMA", "Aviso",
                                 f"NCM indisponível (Drop-estoque): {e}")
        except Exception as e:
            self._adicionar_erro("SISTEMA", "Aviso",
                                 f"Falha ao carregar NCM: {e}")
        return True

    def _montar_dados_asin(self, asin: str,
                           sku_original: Optional[str]) -> Dict[str, Any]:
        # Reaproveita toda a lógica do ASIN (fixos padrão, preço, medidas);
        # o preço já sai da base FULL porque trocamos carregador_precos.
        dados = super()._montar_dados_asin(asin, sku_original)

        # Sobrescreve os fixos específicos do FULL.
        dados.update(self.config.valores_fixos_full)

        # NCM por linha (a partir do SKU raiz).
        if sku_original:
            ncm = self.carregador_ncm.obter_ncm(sku_original)
            if ncm:
                dados['Código NCM'] = ncm
            else:
                self._adicionar_erro(sku_original, "Aviso",
                                     "NCM não encontrado na Drop-estoque")

        return dados
