# ==============================================================================
# CONFIGURAÇÕES GLOBAIS DO SISTEMA
# ==============================================================================
# Este módulo contém todas as configurações, constantes e mapeamentos
# utilizados pelo sistema de criação de planilhas Amazon.
#
# Organização:
#   - Caminhos de arquivos
#   - Mapeamento de prefixos por conta
#   - Valores fixos por categoria
#   - Configurações de colunas
# ==============================================================================

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


@dataclass
class Configuracoes:
    """
    Classe central de configurações do sistema.
    
    Contém todos os parâmetros, caminhos e mapeamentos necessários
    para o funcionamento do processador de planilhas Amazon.
    
    Attributes:
        usuario_home: Caminho do diretório home do usuário
        arquivo_precificacao: Nome do arquivo local de preços
        arquivo_descricao: Nome do arquivo local de descrições
        arquivo_remover: Nome do arquivo de termos a remover
        arquivo_substituir: Nome do arquivo de termos a substituir
    """
    
    # -------------------------------------------------------------------------
    # CAMINHOS DE ARQUIVOS LOCAIS
    # -------------------------------------------------------------------------
    # Podem ser configurados via arquivo .env na raiz do projeto
    # -------------------------------------------------------------------------
    
    usuario_home: str = field(default_factory=lambda: os.path.expanduser("~"))
    arquivo_precificacao: str = field(default_factory=lambda: os.getenv("ARQUIVO_PRECIFICACAO", "Precificacao.xlsx"))
    arquivo_descricao: str = field(default_factory=lambda: os.getenv("ARQUIVO_DESCRICAO", "DESCRIÇÃO.xlsx"))
    arquivo_remover: str = field(default_factory=lambda: os.getenv("ARQUIVO_REMOVER", "termos_remover.txt"))
    arquivo_substituir: str = field(default_factory=lambda: os.getenv("ARQUIVO_SUBSTITUIR", "termos_substituir.txt"))

    # --- Modalidade FULL (isolada do modelo normal) ---
    # Base de preço própria (aba CLA) e planilha de NCM (Drop-estoque).
    arquivo_precificacao_full: str = field(default_factory=lambda: os.getenv("ARQUIVO_PRECIFICACAO_FULL", "Precificacao Amazon - Full.xlsx"))
    aba_precificacao_full: str = field(default_factory=lambda: os.getenv("ABA_PRECIFICACAO_FULL", "CLA"))
    arquivo_drop_estoque: str = field(default_factory=lambda: os.getenv("ARQUIVO_DROP_ESTOQUE", "Drop estoque.xlsx"))

    @property
    def usar_api_descricao(self) -> bool:
        """A base de Descrição vem da API do AgentedeTitulos (título, descrição,
        peso, medidas e bullets) **quando há `TITULOS_API_KEY`** — nesse caso a
        planilha DESCRIÇÃO.xlsx fica de lado, como desejado.

        Sem a chave, NÃO há como consultar a API, então cai na planilha local
        (fallback de segurança — evita gerar planilha sem descrição/medidas).
        `USAR_PLANILHA_DESCRICAO=1` força a planilha mesmo com a chave presente.
        """
        if (os.getenv("USAR_PLANILHA_DESCRICAO") or "").strip().lower() in ("1", "true", "sim"):
            return False
        return bool((os.getenv("TITULOS_API_KEY") or "").strip())
    
    # -------------------------------------------------------------------------
    # CAMINHOS ONEDRIVE (Sincronização automática)
    # -------------------------------------------------------------------------
    
    @property
    def caminhos_precificacao_onedrive(self) -> List[str]:
        """
        Retorna lista de possíveis caminhos para o arquivo de precificação no OneDrive.

        Prioridade (em ordem):
          1. Valores definidos no JSON (via GerenciadorConfig)
          2. Variáveis ONEDRIVE_PRECIFICACAO_1..5 do .env
          3. Padrões hard-coded

        Para cada caminho relativo, também gera a versão absoluta com o home do usuário.
        """
        caminhos = []

        override = getattr(self, "_caminhos_onedrive_override", None)
        if override:
            origem = list(override)
        else:
            padroes = {
                1: r"OneDrive - Top Shop\Criação de Anúncios - Documentos\Precificacao Amazon.xlsx",
                2: r"OneDrive\Criação de Anúncios - Documentos\Precificacao Amazon.xlsx",
            }
            origem = []
            for i in range(1, 6):
                caminho = os.getenv(f"ONEDRIVE_PRECIFICACAO_{i}", padroes.get(i, ""))
                if caminho and caminho.strip():
                    origem.append(caminho.strip())

        for caminho in origem:
            caminhos.append(caminho)
            if not os.path.isabs(caminho):
                caminhos.append(os.path.join(self.usuario_home, caminho))

        return caminhos
    
    # -------------------------------------------------------------------------
    # URL BASE PARA IMAGENS
    # -------------------------------------------------------------------------
    # Pode ser configurada via arquivo .env
    # -------------------------------------------------------------------------
    
    url_base_imagens: str = field(default_factory=lambda: os.getenv("URL_BASE_IMAGENS", "https://topshop-tiny.com.br/wp-content/uploads/tiny"))
    
    # -------------------------------------------------------------------------
    # MAPEAMENTO: PREFIXO SKU -> NOME DA CONTA
    # -------------------------------------------------------------------------
    # Define qual coluna de preço usar baseado no prefixo do SKU
    # Exemplo: SKU "NOGO-ABC123" usa a coluna "Nogora" da planilha de preços
    # -------------------------------------------------------------------------
    
    mapa_prefixo_conta: Dict[str, str] = field(default_factory=lambda: {
        "ATIV-":  "Ativa",
        "ATNC-":  "ATN",
        "BET-":   "Beta",
        "BOX2-":  "Box2Brasil",
        "EASYT-": "Easytech",
        "EVERG-": "Evergreen",
        "FINT-":  "Fintech",
        "FRIS-":  "Frisco",
        "INFIN-": "Infinyshop",
        "JACI-":  "JACITARA",
        "MZIA-":  "Manzia",
        "NOGO-":  "Nogora",
        "RAQ-":   "Raquena",
        "TECH-":  "Tech Place",
        "VIANN-": "Vianeny",
        "VERD-":  "Verdal",
        "TACN-":  "TACNAR"
    })

    # -------------------------------------------------------------------------
    # MAPEAMENTO: PREFIXO SKU CLA -> COLUNA DE PREÇO (Modalidade FULL)
    # -------------------------------------------------------------------------
    # O FULL usa o modelo CONTA-CLA (ex.: BOX-CLA-3047). Os prefixos diferem
    # dos do modelo normal (ex.: normal ATNC-/BOX2-/EASYT-/INFIN- vs CLA
    # ATN-CLA-/BOX-CLA-/EASY-CLA-/INF-CLA-), por isso há um mapa próprio.
    # O valor é o NOME DA COLUNA na aba CLA da "Precificacao Amazon - Full".
    # Verdal e Tacnar ainda NÃO têm coluna na precificação → preço fica vazio
    # (serão adicionadas no futuro; o lookup simplesmente não encontra a coluna).
    # -------------------------------------------------------------------------

    mapa_prefixo_conta_full: Dict[str, str] = field(default_factory=lambda: {
        "ATIV-CLA-":  "Ativa",
        "ATN-CLA-":   "ATN",
        "BET-CLA-":   "Beta",
        "BOX-CLA-":   "Box2Brasil",
        "EASY-CLA-":  "Easytech",
        "EVERG-CLA-": "Evergreen",
        "FINT-CLA-":  "Fintech",
        "FRIS-CLA-":  "Frisco",
        "INF-CLA-":   "Infinyshop",
        "JACI-CLA-":  "JACITARA",
        "MZIA-CLA-":  "Manzia",
        "NOGO-CLA-":  "Nogora",
        "RAQ-CLA-":   "Raquena",
        "TECH-CLA-":  "Tech Place",
        "VIANN-CLA-": "Vianney",
        "VERD-CLA-":  "Verdal",   # sem coluna ainda -> preço vazio
        "TACN-CLA-":  "Tacnar",   # sem coluna ainda -> preço vazio
    })

    # -------------------------------------------------------------------------
    # VALORES FIXOS PADRÃO (Aplicados a todas as categorias)
    # -------------------------------------------------------------------------
    # Estes valores são inseridos automaticamente nas colunas correspondentes
    # do template, quando o nome da coluna coincide com a chave do dicionário.
    # -------------------------------------------------------------------------
    
    valores_fixos_padrao: Dict[str, str] = field(default_factory=lambda: {
        # --- Ação e Tipo ---
        'Ação de oferta': "Criar ou substituir (atualização completa)",
        'Tipo de produto': "AUDIO_OR_VIDEO",
        'Tipo de ID do produto': "EAN",
        'Caminhos de Navegação Recomendados': "Eletrônicos e Tecnologia (16209063011)",
        
        # --- Condição e Envio ---
        'Condição do Produto': "Novo",
        'Condição do item': "Novo",
        'Código do canal de processamento (BR)': "DEFAULT",
        'Tempo de manuseio': "DEFAULT",
        'Quantidade (BR)': "0",
        'Quantidade': "0",
        'Grupo de envio de mercadorias (BR)': "FM Transportes Frete Grátis",
        'Nome do grupo de envio do comerciante': "FM Transportes Frete Grátis",
        
        # --- Detalhes do Produto ---
        'Número de itens': "1",
        'Quantidade de itens': "1",
        'Componentes incluídos': "1",
        'Fonte de energia': "Não aplicável",
        'País de origem': "Brasil",
        'Garantia do fabricante: tipo de garantia': "Não aplicável",
        'Descrição da garantia': "90 Dias",
        'Descrição da garantia do fabricante': "90 dias",
        'Baterias são necessárias?': "Não",
        'Regulamentações de produtos perigosos': "Não aplicável",
        'Certificação de teste externa': "INMETRO: 0000; ANATEL: 0000; Não aplicável",
        
        # --- Unidades de Medida ---
        'Unidade de comprimento do pacote': "Centímetros",
        'Unidade de largura do pacote': "Centímetros",
        'Unidade de altura do pacote': "Centímetros",
        'Unidade de peso do pacote': "Quilogramas",
        'Unidade de peso do item': "Quilogramas",
        
        # --- Fallbacks (Nomes alternativos) ---
        'comprimento_da_embalagem_unidade_de_medida': "Centímetros",
        'largura_da_embalagem_unidade_de_medida': "Centímetros",
        'altura_da_embalagem_unidade_de_medida': "Centímetros",
        'peso_do_item_unidade_de_medida': "Quilogramas",
        'unidade_de_medida_do_peso_do_item': "Quilogramas"
    })

    # -------------------------------------------------------------------------
    # VALORES FIXOS — MODALIDADE FULL (sobrescrevem os padrão)
    # -------------------------------------------------------------------------
    # Aplicados por cima de `valores_fixos_padrao` no ProcessadorFULL. O FULL é
    # enviado pela Logística da Amazon (FBA), então o canal e o modelo de envio
    # mudam; a origem da mercadoria é fixa em 1. O Código NCM NÃO entra aqui —
    # é por linha, vindo da planilha Drop-estoque.
    # -------------------------------------------------------------------------

    valores_fixos_full: Dict[str, str] = field(default_factory=lambda: {
        'Código do canal de processamento (BR)': "Logística da Amazon (AN)",
        'Modelo de Envio (BR)': "Modelo padrão da Amazon",
        'Origem da mercadoria': "1",
        'Quantidade (BR)': "0",
        'Quantidade': "0",
    })

    # -------------------------------------------------------------------------
    # COLUNAS QUE SÓ PREENCHEM A PRIMEIRA OCORRÊNCIA
    # -------------------------------------------------------------------------
    # Algumas colunas aparecem múltiplas vezes no template, mas só devem
    # ser preenchidas na primeira ocorrência (evita duplicação).
    # -------------------------------------------------------------------------
    
    colunas_apenas_primeira_ocorrencia: List[str] = field(default_factory=lambda: [
        "Preço padrão BRL (Vender na Amazon, BR)",
        "Certificação de teste externa",
        "Regulamentações de produtos perigosos",
        "Caminhos de Navegação Recomendados",
        "Componentes incluídos",
        "Quantidade (BR)",
        "Descrição da garantia"
    ])
    
    # -------------------------------------------------------------------------
    # CONFIGURAÇÕES DE MAPEAMENTO DE COLUNAS
    # -------------------------------------------------------------------------
    # Define os possíveis nomes de colunas para cada campo,
    # permitindo flexibilidade entre diferentes templates.
    # -------------------------------------------------------------------------
    
    mapa_colunas_descricao: Dict[str, List[str]] = field(default_factory=lambda: {
        'sku':     ['SKU', 'K2 - SKU', 'K3 - SKU'],
        'titulo':  ['TÍTULO AMAZON', 'Título MLB', 'Nome do Item', 'Nome do Produto'],
        'modelo':  ['MODELO REF.', 'REF-ASIN', 'Modelo', 'NÚMERO DA PEÇA',
                    'Número da peça', 'Número da peça do fabricante',
                    'Número da peça fabricante'],
        'ean':     ['EAN', 'GTIN', 'Código de Barras'],
        'peso':    ['PESO', 'Peso (kg)'],
        'comp':    ['COMP.', 'COMP', 'Comprimento', 'C'],
        'larg':    ['LARG.', 'LARG', 'Largura', 'L'],
        'alt':     ['ALT.', 'ALT', 'Altura', 'A'],
        'desc':    ['DESCRIÇÃO', 'Descrição', 'Desc'],
        'topico1': ['1. Marcador', 'Marcador 1', 'Bullet 1'],
        'topico2': ['2. Marcador', 'Marcador 2', 'Bullet 2'],
        'topico3': ['3. Marcador', 'Marcador 3', 'Bullet 3'],
        'topico4': ['4. Marcador', 'Marcador 4', 'Bullet 4'],
        'topico5': ['5. Marcador', 'Marcador 5', 'Bullet 5'],
    })

    # -------------------------------------------------------------------------
    # MAPEAMENTO DE COLUNAS — PLANILHA DE PRECIFICAÇÃO
    # -------------------------------------------------------------------------
    # Define os possíveis nomes para a coluna de SKU (chave de busca) e para a
    # coluna de Preço Padrão. Editável via tela de Configurações (admin).
    # As colunas por conta continuam vindo de `mapa_prefixo_conta`.
    # -------------------------------------------------------------------------

    mapa_colunas_precificacao: Dict[str, List[str]] = field(default_factory=lambda: {
        'sku':           ['SKU', 'Chave', 'Código', 'Item'],
        'preco_padrao':  ['Padrão', 'Preço Padrão', 'Standard'],
    })
    
    # -------------------------------------------------------------------------
    # PALAVRAS-CHAVE PARA IDENTIFICAÇÃO DE COLUNAS
    # -------------------------------------------------------------------------
    
    palavras_chave_imagem_principal: List[str] = field(default_factory=lambda: [
        'main image', 'main', 'url imagem principal', 'url da imagem principal'
    ])
    
    palavras_chave_imagem_secundaria: List[str] = field(default_factory=lambda: [
        'outro', 'other image', 'imagem', 'image'
    ])
    
    palavras_chave_texto_limpeza: List[str] = field(default_factory=lambda: [
        'nome do item', 'nome do produto', 'titulo', 'title',
        'descrição', 'descricao', 'description',
        'topico', 'bullet', 'marcador', 'ponto de destaque'
    ])

    # -------------------------------------------------------------------------
    # APLICAÇÃO DE CONFIGURAÇÃO PERSISTIDA (JSON)
    # -------------------------------------------------------------------------

    def aplicar_gerenciador(self, gerenciador: Any) -> "Configuracoes":
        """
        Sobrescreve campos da configuração com valores vindos do
        GerenciadorConfig (JSON editado via UI).

        - Caminhos de arquivos (precificação/descrição/textos)
        - URL base de imagens
        - Caminhos OneDrive (cache em atributo `_caminhos_onedrive_override`)
        - Mapeamentos estáticos customizados (mesclados em valores_fixos_padrao)
        """
        self.arquivo_precificacao = gerenciador.get("arquivo_precificacao", self.arquivo_precificacao)
        self.arquivo_precificacao_full = gerenciador.get("arquivo_precificacao_full", self.arquivo_precificacao_full)
        self.aba_precificacao_full = gerenciador.get("aba_precificacao_full", self.aba_precificacao_full)
        self.arquivo_drop_estoque = gerenciador.get("arquivo_drop_estoque", self.arquivo_drop_estoque)
        self.arquivo_descricao = gerenciador.get("arquivo_descricao", self.arquivo_descricao)
        self.arquivo_remover = gerenciador.get("arquivo_remover", self.arquivo_remover)
        self.arquivo_substituir = gerenciador.get("arquivo_substituir", self.arquivo_substituir)
        self.url_base_imagens = gerenciador.get("url_base_imagens", self.url_base_imagens)

        # Override dos caminhos OneDrive
        caminhos = gerenciador.caminhos_onedrive()
        if caminhos:
            self._caminhos_onedrive_override = caminhos
        else:
            self._caminhos_onedrive_override = None

        # Mescla valores fixos customizados (sobrescreve padrões com mesmo nome)
        customizados = gerenciador.valores_fixos_customizados()
        if customizados:
            self.valores_fixos_padrao.update(customizados)

        # Remove valores fixos que o usuário excluiu via painel
        excluidos = gerenciador.get("valores_fixos_excluidos", [])
        for chave in excluidos:
            self.valores_fixos_padrao.pop(chave, None)

        # Override de mapa de colunas (sinônimos por campo lógico)
        try:
            mapa_colunas = gerenciador.mapa_colunas_descricao()
        except AttributeError:
            mapa_colunas = {}
        if mapa_colunas:
            for chave, lista in mapa_colunas.items():
                if lista:
                    self.mapa_colunas_descricao[chave] = list(lista)
        for chave in gerenciador.get("mapa_colunas_excluidos", []):
            self.mapa_colunas_descricao.pop(chave, None)

        # Override de mapa de prefixo→conta
        try:
            mapa_prefixo = gerenciador.mapa_prefixo_conta()
        except AttributeError:
            mapa_prefixo = {}
        if mapa_prefixo:
            for prefixo, conta in mapa_prefixo.items():
                self.mapa_prefixo_conta[prefixo] = conta
        for prefixo in gerenciador.get("prefixos_excluidos", []):
            self.mapa_prefixo_conta.pop(prefixo, None)

        # Override de mapa de colunas da Precificação
        try:
            mapa_precificacao = gerenciador.mapa_colunas_precificacao()
        except AttributeError:
            mapa_precificacao = {}
        if mapa_precificacao:
            for chave, lista in mapa_precificacao.items():
                if lista:
                    self.mapa_colunas_precificacao[chave] = list(lista)
        for chave in gerenciador.get("mapa_precificacao_excluidos", []):
            self.mapa_colunas_precificacao.pop(chave, None)

        return self


# ==============================================================================
# CONFIGURAÇÃO ESPECÍFICA POR CATEGORIA
# ==============================================================================
# Permite estender as configurações padrão para categorias específicas
# ==============================================================================

@dataclass
class ConfiguracaoBrinquedos(Configuracoes):
    """Configurações específicas para categoria Brinquedos."""
    
    def __post_init__(self):
        self.valores_fixos_padrao.update({
            'Tipo de produto': "TOYS",
            'Faixa etária recomendada': "3+",
            'Caminhos de Navegação Recomendados': "Brinquedos e Jogos"
        })


@dataclass
class ConfiguracaoSuplemento(Configuracoes):
    """Configurações específicas para categoria Suplementos."""
    
    def __post_init__(self):
        self.valores_fixos_padrao.update({
            'Tipo de produto': "HEALTH_PERSONAL_CARE",
            'Caminhos de Navegação Recomendados': "Saúde e Cuidados Pessoais"
        })


@dataclass
class ConfiguracaoPotesVidro(Configuracoes):
    """Configurações específicas para categoria Potes de Vidro."""
    
    def __post_init__(self):
        self.valores_fixos_padrao.update({
            'Tipo de produto': "HOME",
            'Material': "Vidro",
            'Caminhos de Navegação Recomendados': "Casa e Cozinha"
        })


# ==============================================================================
# INSTÂNCIA GLOBAL PADRÃO
# ==============================================================================

config_padrao = Configuracoes()
