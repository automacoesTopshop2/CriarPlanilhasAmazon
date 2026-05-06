# ==============================================================================
# MAPEADOR DE COLUNAS
# ==============================================================================
# Classe responsável por mapear colunas de templates Excel de forma dinâmica.
#
# Funcionalidades:
#   - Leitura dinâmica de cabeçalhos (linha configurável)
#   - Normalização de nomes de colunas
#   - Suporte a colunas duplicadas (múltiplas ocorrências)
#   - Aliases/sinônimos para nomes de colunas
#   - Identificação automática da primeira linha de dados
# ==============================================================================

from openpyxl.utils import column_index_from_string
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

from ..utils import Utilitarios


@dataclass
class InfoColuna:
    """
    Informações detalhadas sobre uma coluna mapeada.
    
    Attributes:
        nome_original: Nome original da coluna como aparece no Excel
        nome_normalizado: Nome normalizado para comparação
        indices: Lista de índices onde a coluna aparece (1-based)
        apenas_primeira: Se deve preencher apenas a primeira ocorrência
    """
    nome_original: str
    nome_normalizado: str
    indices: List[int] = field(default_factory=list)
    apenas_primeira: bool = False


class MapeadorColunas:
    """
    Mapeia colunas de templates Excel de forma dinâmica e inteligente.
    
    Esta classe é responsável por:
    - Ler cabeçalhos de templates em linhas configuráveis
    - Normalizar nomes de colunas para comparação
    - Tratar aliases/sinônimos de nomes
    - Identificar colunas duplicadas
    - Encontrar automaticamente a primeira linha de dados
    
    Attributes:
        mapa: Dicionário {nome_normalizado: [lista_de_indices]}
        mapa_detalhado: Dicionário {nome_normalizado: InfoColuna}
        linha_cabecalho: Número da linha do cabeçalho
        primeira_linha_dados: Número da primeira linha de dados
    """
    
    # -------------------------------------------------------------------------
    # ALIASES (Sinônimos para nomes de colunas)
    # -------------------------------------------------------------------------
    # Permite reconhecer diferentes nomes como sendo a mesma coluna
    # -------------------------------------------------------------------------
    
    ALIASES: Dict[str, str] = {
        # SKU
        'sku do vendedor': 'sku',
        'vendedor sku': 'sku',
        'item_sku': 'sku',
        'seller sku': 'sku',
        
        # Preço
        'preco': 'preço padrão brl (vender na amazon, br)',
        'standard_price': 'preço padrão brl (vender na amazon, br)',
        'preço padrão': 'preço padrão brl (vender na amazon, br)',
        'price': 'preço padrão brl (vender na amazon, br)',
        
        # Descrição
        'product_description': 'descrição do produto',
        'descricao': 'descrição do produto',
        
        # Marca
        'brand': 'nome da marca',
        'marca': 'nome da marca',
        
        # Título
        'title': 'nome do item',
        'titulo': 'nome do item',
        'item_name': 'nome do item',
    }
    
    def __init__(self):
        """Inicializa o mapeador de colunas."""
        self.mapa: Dict[str, List[int]] = {}
        self.mapa_detalhado: Dict[str, InfoColuna] = {}
        self.linha_cabecalho: int = 4
        self.primeira_linha_dados: int = 8
        self._planilha = None
    
    def mapear_template(self, planilha, linha_cabecalho: int = 4,
                        detectar_primeira_linha: bool = False) -> Dict[str, List[int]]:
        """
        Mapeia as colunas de um template Excel.
        
        Lê a linha especificada como cabeçalho e cria um mapeamento
        de nomes de colunas para índices (1-based).
        
        Args:
            planilha: Objeto worksheet do openpyxl
            linha_cabecalho: Número da linha com os nomes das colunas
            detectar_primeira_linha: Se True, detecta automaticamente a 
                primeira linha de dados. Se False (padrão), mantém o valor
                fixo definido no __init__ (evita bugs com templates que 
                têm dados de exemplo).
            
        Returns:
            Dicionário {nome_normalizado: [indices]}
        """
        self.mapa.clear()
        self.mapa_detalhado.clear()
        self.linha_cabecalho = linha_cabecalho
        self._planilha = planilha
        
        # Lê a linha de cabeçalho
        for celula in planilha[linha_cabecalho]:
            if celula.value:
                # Normaliza o nome
                nome_original = str(celula.value)
                nome_normalizado = Utilitarios.normalizar_texto(nome_original)
                
                # Aplica aliases se houver
                nome_normalizado = self._aplicar_alias(nome_normalizado)
                
                # Obtém o índice numérico (1-based)
                indice_coluna = (
                    celula.column if isinstance(celula.column, int)
                    else column_index_from_string(celula.column)
                )
                
                # Adiciona ao mapeamento simples
                if nome_normalizado not in self.mapa:
                    self.mapa[nome_normalizado] = []
                self.mapa[nome_normalizado].append(indice_coluna)
                
                # Adiciona ao mapeamento detalhado
                if nome_normalizado not in self.mapa_detalhado:
                    self.mapa_detalhado[nome_normalizado] = InfoColuna(
                        nome_original=nome_original,
                        nome_normalizado=nome_normalizado,
                        indices=[]
                    )
                self.mapa_detalhado[nome_normalizado].indices.append(indice_coluna)
        
        # Detecta a primeira linha de dados APENAS se solicitado
        # Por padrão (detectar_primeira_linha=False), mantém o valor fixo
        if detectar_primeira_linha:
            self.primeira_linha_dados = self._detectar_primeira_linha_dados(planilha)
        # Caso contrário, mantém self.primeira_linha_dados com o valor do __init__ 
        # que é 8 por padrão (correto para templates SKU)
        
        return self.mapa
    
    def _aplicar_alias(self, nome: str) -> str:
        """
        Aplica alias ao nome da coluna se houver correspondência.
        
        Args:
            nome: Nome normalizado da coluna
            
        Returns:
            Nome com alias aplicado ou o nome original
        """
        return self.ALIASES.get(nome, nome)
    
    def _detectar_primeira_linha_dados(self, planilha, 
                                        max_linhas_busca: int = 20) -> int:
        """
        Detecta automaticamente a primeira linha que contém dados.
        
        Procura pela primeira linha após o cabeçalho que contenha
        valores não-vazios em colunas importantes (SKU, etc.).
        
        Args:
            planilha: Objeto worksheet do openpyxl
            max_linhas_busca: Máximo de linhas após cabeçalho para buscar
            
        Returns:
            Número da primeira linha de dados
        """
        # Encontra o índice da coluna SKU (se mapeada)
        indice_sku = None
        for nome in ['sku', 'sku do vendedor', 'seller sku']:
            if nome in self.mapa and self.mapa[nome]:
                indice_sku = self.mapa[nome][0]
                break
        
        # Se não encontrou SKU, usa a primeira coluna com dados
        if indice_sku is None:
            indice_sku = 1
        
        # Procura a primeira linha com dados
        linha_inicio = self.linha_cabecalho + 1
        linha_fim = linha_inicio + max_linhas_busca
        
        for numero_linha in range(linha_inicio, linha_fim):
            try:
                celula = planilha.cell(row=numero_linha, column=indice_sku)
                if celula.value is not None and str(celula.value).strip():
                    return numero_linha
            except Exception:
                continue
        
        # Fallback: linha após cabeçalho + 3 (padrão Amazon)
        return self.linha_cabecalho + 4
    
    def obter_indices(self, nome_coluna: str) -> List[int]:
        """
        Obtém os índices de uma coluna pelo nome.
        
        Args:
            nome_coluna: Nome da coluna (será normalizado)
            
        Returns:
            Lista de índices ou lista vazia
        """
        nome_normalizado = Utilitarios.normalizar_texto(nome_coluna)
        nome_normalizado = self._aplicar_alias(nome_normalizado)
        return self.mapa.get(nome_normalizado, [])
    
    def obter_primeiro_indice(self, nome_coluna: str) -> Optional[int]:
        """
        Obtém o primeiro índice de uma coluna pelo nome.
        
        Args:
            nome_coluna: Nome da coluna (será normalizado)
            
        Returns:
            Primeiro índice ou None
        """
        indices = self.obter_indices(nome_coluna)
        return indices[0] if indices else None
    
    def coluna_existe(self, nome_coluna: str) -> bool:
        """
        Verifica se uma coluna existe no mapeamento.
        
        Args:
            nome_coluna: Nome da coluna (será normalizado)
            
        Returns:
            True se a coluna existe
        """
        return len(self.obter_indices(nome_coluna)) > 0
    
    def listar_colunas(self) -> List[str]:
        """
        Lista todos os nomes de colunas mapeadas.
        
        Returns:
            Lista de nomes normalizados
        """
        return list(self.mapa.keys())
    
    def obter_colunas_tipo(self, palavras_chave: List[str]) -> List[int]:
        """
        Obtém índices de todas as colunas que contenham palavras-chave.
        
        Útil para encontrar colunas de imagem, tópicos, etc.
        
        Args:
            palavras_chave: Lista de palavras para buscar
            
        Returns:
            Lista de índices encontrados
        """
        indices_encontrados = []
        
        for nome_coluna, indices in self.mapa.items():
            if any(palavra in nome_coluna for palavra in palavras_chave):
                indices_encontrados.extend(indices)
        
        return list(set(indices_encontrados))  # Remove duplicatas
    
    def mapear_input(self, planilha, linha_cabecalho: int = 1) -> Dict[str, int]:
        """
        Mapeia as colunas de uma planilha de entrada (input).
        
        Diferente do template, a planilha de entrada geralmente tem
        apenas uma ocorrência de cada coluna.
        
        Args:
            planilha: Objeto worksheet do openpyxl
            linha_cabecalho: Número da linha com os nomes
            
        Returns:
            Dicionário {nome_upper: indice}
        """
        mapa_input = {}
        
        linha = next(planilha.iter_rows(
            min_row=linha_cabecalho, 
            max_row=linha_cabecalho, 
            values_only=True
        ))
        
        for indice, valor in enumerate(linha):
            if valor:
                nome = str(valor).strip().upper()
                mapa_input[nome] = indice
        
        return mapa_input
    
    def encontrar_coluna_input(self, mapa_input: Dict[str, int], 
                                nomes_possiveis: List[str]) -> Optional[int]:
        """
        Encontra o índice de uma coluna no mapa de input.
        
        Args:
            mapa_input: Mapeamento {nome: indice}
            nomes_possiveis: Lista de nomes a tentar
            
        Returns:
            Índice encontrado ou None
        """
        for nome in nomes_possiveis:
            if nome.upper() in mapa_input:
                return mapa_input[nome.upper()]
        return None
