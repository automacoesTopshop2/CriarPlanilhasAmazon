# ==============================================================================
# CARREGADOR DE DESCRIÇÃO — FONTE: API AgentedeTitulos
# ==============================================================================
# Substitui a leitura da planilha DESCRIÇÃO.xlsx por consultas à API do
# AgentedeTitulos (banco unificado de títulos/descrições), SEM mudar o restante
# do fluxo. Herda de CarregadorDescricao e reaproveita TODA a lógica de Kit
# (K2-, K-A-B): apenas troca a ORIGEM dos dados (preenche `self.dados` sob
# demanda via API em vez de carregar a planilha inteira).
#
# Importante — só trazemos da API os campos que JÁ vinham da planilha de
# descrição: título, descrição, modelo, peso, medidas e tópicos (marcadores).
# Marca e EAN continuam vindo do que o operador preencher (o EAN do produto
# NÃO é puxado da API aqui — `ean` fica vazio de propósito).
# ==============================================================================

import re
from datetime import datetime
from typing import List, Optional

from .descricao import CarregadorDescricao, DadosProduto
from ..utils import Utilitarios
from .. import titulos_client


class CarregadorDescricaoAPI(CarregadorDescricao):
    """Carregador de descrição que consulta a API do AgentedeTitulos.

    Carregamento é *lazy*: nada é pré-carregado; cada SKU (e os componentes de
    um Kit) é buscado sob demanda e cacheado em `self.dados`, de onde a lógica
    herdada (`obter_produto` / `_calcular_kit`) opera normalmente.
    """

    # EAN não é puxado da API — continua vindo do operador (input da planilha
    # de SKUs). Flag explícita para facilitar reverter, se um dia quiserem.
    INCLUIR_EAN_DA_API = False

    def __init__(self, config=None):
        super().__init__(config)
        self._nao_encontrados: set[str] = set()

    # -- substitui a dependência de arquivo local -----------------------------
    def arquivo_existe(self) -> bool:  # a fonte é a API, não um arquivo
        return True

    def carregar(self, forcar_recarga: bool = False) -> bool:
        """Marca como pronto (lazy). Não baixa o catálogo inteiro."""
        if self._carregado and not forcar_recarga:
            return True
        self._erros.clear()
        if forcar_recarga:
            self.dados.clear()
            self._nao_encontrados.clear()
        self._carregado = True
        self._data_carregamento = datetime.now()
        return True

    # -- busca sob demanda ----------------------------------------------------
    def obter_produto(self, sku: str) -> Optional[DadosProduto]:
        if not self._carregado:
            return None
        sku_base = Utilitarios.tratar_sku(
            sku, list(self.config.mapa_prefixo_conta.keys())
        )
        if not sku_base:
            return None
        # Garante que o SKU (ou os componentes do Kit) estejam em self.dados,
        # então delega para a lógica herdada (busca direta + cálculo de Kit).
        self._garantir_carregado(sku_base)
        return super().obter_produto(sku)

    def _garantir_carregado(self, sku_base: str) -> None:
        prefixos = list(self.config.mapa_prefixo_conta.keys())
        componentes = self._skus_componentes(sku_base)
        # Kit não existe no catálogo (1 linha por produto); buscamos só os
        # componentes. Produto simples: buscamos ele mesmo.
        alvos = componentes if componentes else [sku_base]
        for alvo in alvos:
            chave = Utilitarios.tratar_sku(alvo, prefixos)
            if not chave or chave in self.dados or chave in self._nao_encontrados:
                continue
            row = titulos_client.consultar_sku(chave)
            dados = self._dados_de_row(row) if row else None
            if dados:
                dados.sku_base = chave
                self.dados[chave] = dados
            else:
                self._nao_encontrados.add(chave)

    def _dados_de_row(self, row: dict) -> Optional[DadosProduto]:
        sku = str(row.get("sku") or "").strip()
        sku_base = Utilitarios.tratar_sku(
            sku, list(self.config.mapa_prefixo_conta.keys())
        )
        if not sku_base:
            return None
        # Título: preferimos o da Amazon; cai para o do ML se vazio.
        titulo = (row.get("titulo_amazon") or row.get("titulo_mlb") or "").strip()
        marcadores = [
            str(m).strip() for m in (row.get("marcadores") or []) if str(m).strip()
        ]
        return DadosProduto(
            sku_base=sku_base,
            titulo=titulo,
            descricao=(row.get("descricao") or "").strip(),
            modelo=(row.get("modelo_ref") or "").strip(),
            ean=(str(row.get("ean") or "").strip() if self.INCLUIR_EAN_DA_API else ""),
            peso=str(row.get("peso") or "").strip(),
            comprimento=str(row.get("comprimento") or "").strip(),
            largura=str(row.get("largura") or "").strip(),
            altura=str(row.get("altura") or "").strip(),
            topicos=marcadores,
        )

    @staticmethod
    def _skus_componentes(sku_base: str) -> List[str]:
        """SKUs-componentes a buscar quando o SKU é um Kit (espelha a lógica de
        _calcular_kit do pai). Retorna [] para produto simples."""
        s = (sku_base or "").strip()
        # Kx-...  (ex.: K2-2999, K5-6384-6392)
        match = re.match(r"^K(\d+)-(.+)$", s, re.IGNORECASE)
        if match:
            resto = match.group(2).strip().upper()
            if "-V" in resto:
                resto = resto.split("-V")[0]
            comps = [resto]
            if "-" in resto:
                comps.extend(p for p in resto.split("-") if p)
            return comps
        # K-A-B-C  (produtos diferentes)
        if s.upper().startswith("K-"):
            return [p for p in s.split("-")[1:] if p]
        return []

    def limpar_cache(self) -> None:
        super().limpar_cache()
        self._nao_encontrados.clear()
