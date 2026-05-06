# ==============================================================================
# SISTEMA DE PLANILHAS AMAZON - APLICAÇÃO PRINCIPAL
# ==============================================================================
# Versão: 6.1 (Com Logs em Tempo Real)
# 
# Este é o ponto de entrada da aplicação Streamlit.
# A aplicação foi completamente refatorada com:
#   - Arquitetura modular (core/, ui/)
#   - Classes e métodos organizados
#   - LOGS EM TEMPO REAL durante processamento
#   - Tratamento de erros robusto com traceback
#   - Interface de usuário melhorada
#
# Estrutura do projeto:
#   - core/config.py       : Configurações e constantes
#   - core/utils.py        : Funções utilitárias
#   - core/carregadores/   : Carregadores de dados (preços, descrição)
#   - core/processadores/  : Processadores de templates (SKU, ASIN, Limpeza)
#   - core/mapeadores/     : Mapeamento de colunas
#   - ui/                  : Componentes de interface
# ==============================================================================

import os
import sys

# Raiz do projeto é o pai de site/ — garante CWD e importação de core/
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_root)
if _root not in sys.path:
    sys.path.insert(0, _root)

import streamlit as st
import pandas as pd
import traceback
from datetime import datetime

# Importações do sistema
from core.config import Configuracoes
from core.processadores import ProcessadorSKU, ProcessadorASIN, ProcessadorLimpeza
from ui import SidebarUI, ComponentesUI


# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA
# ==============================================================================

st.set_page_config(
    page_title="Sistema de Planilhas Amazon", 
    page_icon="📦", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# Injeta estilos customizados
ComponentesUI.injetar_estilos()


# ==============================================================================
# INICIALIZAÇÃO
# ==============================================================================

# Configurações globais
config = Configuracoes()

# Componentes de UI
sidebar = SidebarUI(config)


# ==============================================================================
# HEADER PRINCIPAL
# ==============================================================================

st.title("📦 Sistema de Planilhas Amazon")
st.markdown("**Versão 6.1** - Com logs em tempo real")
st.markdown("---")


# ==============================================================================
# SIDEBAR E NAVEGAÇÃO
# ==============================================================================

menu_selecionado = sidebar.renderizar()


# ==============================================================================
# MÓDULO 1: CRIAR POR SKU
# ==============================================================================

if menu_selecionado == "1. Criar por SKU":
    st.header("🏭 Criação via SKU")
    
    # Verifica bases de dados
    if not sidebar.todas_bases_prontas():
        ComponentesUI.aviso_bases_incompletas()
    
    # Seleção de categoria
    categoria = st.selectbox(
        "Selecione a Categoria:", 
        ["Criar Padrão", "Criar Brinquedos", "Criar Potes de Vidro", "Criar Suplementos"],
        help="A categoria determina valores fixos específicos para o template",
        key="categoria_sku"
    )
    
    st.markdown("---")
    
    # Informações sobre a categoria
    if categoria == "Criar Padrão":
        ComponentesUI.info_instrucoes(
            "**Modelo Padrão (AUDIO_OR_VIDEO)**\n\n"
            "Faça upload da planilha com os SKUs e do modelo NOGORA para processamento."
        )
    elif categoria == "Criar Brinquedos":
        ComponentesUI.info_instrucoes(
            "**Modelo Brinquedos (TOYS)**\n\n"
            "Categoria em desenvolvimento. Use o modelo padrão por enquanto."
        )
    elif categoria == "Criar Potes de Vidro":
        ComponentesUI.info_instrucoes(
            "**Modelo Potes de Vidro (HOME)**\n\n"
            "Categoria em desenvolvimento. Use o modelo padrão por enquanto."
        )
    elif categoria == "Criar Suplementos":
        ComponentesUI.info_instrucoes(
            "**Modelo Suplementos (HEALTH)**\n\n"
            "Categoria em desenvolvimento. Use o modelo padrão por enquanto."
        )
    
    # Upload de arquivos com keys únicas
    col1, col2 = st.columns(2)
    
    with col1:
        arquivo_sku = st.file_uploader(
            "1. Planilha SKU (Input)", 
            type=["xlsx"],
            key="sku_entrada"
        )
    
    with col2:
        arquivo_template_sku = st.file_uploader(
            "2. Modelo NOGORA (.xlsm)",
            type=["xlsm"],
            key="sku_template"
        )
    
    # Mostra status dos arquivos
    col_status1, col_status2 = st.columns(2)
    with col_status1:
        if arquivo_sku:
            st.success(f"✅ Arquivo carregado: {arquivo_sku.name}")
        else:
            st.info("⏳ Aguardando planilha de SKUs...")
    
    with col_status2:
        if arquivo_template_sku:
            st.success(f"✅ Template carregado: {arquivo_template_sku.name}")
        else:
            st.info("⏳ Aguardando template NOGORA...")
    
    st.markdown("---")
    
    # Botão de processar
    botao_processar_sku = st.button(
        "🚀 PROCESSAR SKUs",
        type="primary",
        use_container_width=True,
        disabled=not (arquivo_sku and arquivo_template_sku),
        key="btn_processar_sku"
    )
    
    if botao_processar_sku:
        if arquivo_sku and arquivo_template_sku:
            st.markdown("---")
            
            # Cria instância do processador
            processador = ProcessadorSKU(config)
            
            # Executa com logs em tempo real
            resultado = ComponentesUI.executar_com_logs_tempo_real(
                processador=processador,
                arquivo_entrada=arquivo_sku,
                arquivo_template=arquivo_template_sku,
                titulo="Processando SKUs..."
            )
            
            # Exibe resultado final
            if resultado:
                ComponentesUI.exibir_resultado_processamento(resultado)
        else:
            ComponentesUI.aviso_arquivos_faltando()


# ==============================================================================
# MÓDULO 2: CRIAR POR ASIN
# ==============================================================================

elif menu_selecionado == "2. Criar por ASIN":
    st.header("⚡ Criação via ASIN")
    
    ComponentesUI.info_instrucoes(
        "**Processamento por ASIN**\n\n"
        "Este módulo processa listas de ASINs existentes, preenchendo apenas "
        "os campos essenciais como preço, medidas e peso.\n\n"
        "**Formato esperado:** Coluna A = ASIN, Coluna B = SKU"
    )
    
    # Upload de arquivos com keys únicas para ASIN
    col1, col2 = st.columns(2)
    
    with col1:
        arquivo_asin = st.file_uploader(
            "1. Lista ASINs (CriarASIN)",
            type=["xlsx"],
            key="asin_entrada"
        )
    
    with col2:
        arquivo_template_asin = st.file_uploader(
            "2. Modelo ListaASINS (.xlsm)",
            type=["xlsm"],
            key="asin_template"
        )
    
    # Mostra status dos arquivos
    col_status1, col_status2 = st.columns(2)
    with col_status1:
        if arquivo_asin:
            st.success(f"✅ Arquivo carregado: {arquivo_asin.name}")
        else:
            st.info("⏳ Aguardando lista de ASINs...")
    
    with col_status2:
        if arquivo_template_asin:
            st.success(f"✅ Template carregado: {arquivo_template_asin.name}")
        else:
            st.info("⏳ Aguardando template ListaASINS...")
    
    st.markdown("---")
    
    # Botão de processar
    botao_processar_asin = st.button(
        "🚀 PROCESSAR ASINs",
        type="primary",
        use_container_width=True,
        disabled=not (arquivo_asin and arquivo_template_asin),
        key="btn_processar_asin"
    )
    
    if botao_processar_asin:
        if arquivo_asin and arquivo_template_asin:
            st.markdown("---")
            
            # Cria instância do processador
            processador = ProcessadorASIN(config)
            
            # Executa com logs em tempo real
            resultado = ComponentesUI.executar_com_logs_tempo_real(
                processador=processador,
                arquivo_entrada=arquivo_asin,
                arquivo_template=arquivo_template_asin,
                titulo="Processando ASINs..."
            )
            
            # Exibe resultado final
            if resultado:
                ComponentesUI.exibir_resultado_processamento(resultado)
        else:
            ComponentesUI.aviso_arquivos_faltando()


# ==============================================================================
# MÓDULO 3: LIMPEZA
# ==============================================================================

elif menu_selecionado == "3. Limpeza":
    st.header("🧹 Ferramenta de Limpeza")
    
    # Instância do processador de limpeza
    processador_limpeza = ProcessadorLimpeza(config)
    
    # Carrega termos existentes
    termos_remover, termos_substituir = processador_limpeza.carregar_termos()
    
    # Layout em duas colunas
    col1, col2 = st.columns(2)
    
    # Coluna 1: Termos a Remover
    with col1:
        st.subheader("🗑️ Remover Termos")
        st.caption("Remove o termo independente de maiúsculas/minúsculas")
        
        # Tabela de termos
        if termos_remover:
            df_remover = pd.DataFrame(termos_remover, columns=["Termo"])
            st.dataframe(df_remover, hide_index=True, use_container_width=True, height=200)
        else:
            st.info("Nenhum termo cadastrado para remoção.")
        
        # Formulário para adicionar
        with st.form("form_remover", clear_on_submit=True):
            novo_termo = st.text_input("Novo termo para remover:", key="input_remover")
            if st.form_submit_button("➕ Adicionar", use_container_width=True):
                if novo_termo:
                    if processador_limpeza.salvar_termo_remover(novo_termo):
                        st.success(f"Termo '{novo_termo}' adicionado!")
                        st.rerun()
                    else:
                        st.error("Erro ao salvar termo.")
    
    # Coluna 2: Termos a Substituir
    with col2:
        st.subheader("🔄 Substituir Termos")
        st.caption("Substitui termo A por B")
        
        # Tabela de termos
        if termos_substituir:
            df_substituir = pd.DataFrame(
                list(termos_substituir.items()), 
                columns=["Antigo", "Novo"]
            )
            st.dataframe(df_substituir, hide_index=True, use_container_width=True, height=200)
        else:
            st.info("Nenhum par de substituição cadastrado.")
        
        # Formulário para adicionar
        with st.form("form_substituir", clear_on_submit=True):
            col_a, col_b = st.columns(2)
            termo_antigo = col_a.text_input("Termo antigo:", key="input_antigo")
            termo_novo = col_b.text_input("Termo novo:", key="input_novo")
            
            if st.form_submit_button("➕ Adicionar", use_container_width=True):
                if termo_antigo and termo_novo:
                    if processador_limpeza.salvar_termo_substituir(termo_antigo, termo_novo):
                        st.success(f"Substituição '{termo_antigo}' → '{termo_novo}' adicionada!")
                        st.rerun()
                    else:
                        st.error("Erro ao salvar substituição.")
    
    st.markdown("---")
    
    # Upload e processamento
    st.subheader("📄 Processar Planilha")
    
    arquivo_limpeza = st.file_uploader(
        "Planilha para limpar:",
        type=["xlsx", "xlsm"],
        help="Envie uma planilha com a aba 'Modelo' para limpeza",
        key="limpeza_entrada"
    )
    
    # Status do arquivo
    if arquivo_limpeza:
        st.success(f"✅ Arquivo carregado: {arquivo_limpeza.name}")
    
    # Botão de processar
    botao_limpar = st.button(
        "🚀 EXECUTAR LIMPEZA",
        type="primary",
        use_container_width=True,
        disabled=not arquivo_limpeza,
        key="btn_limpar"
    )
    
    if botao_limpar:
        if arquivo_limpeza:
            st.markdown("---")
            
            # Executa com logs em tempo real
            resultado = ComponentesUI.executar_com_logs_tempo_real(
                processador=processador_limpeza,
                arquivo_entrada=arquivo_limpeza,
                arquivo_template=None,
                titulo="Executando limpeza..."
            )
            
            # Exibe resultado final
            if resultado:
                ComponentesUI.exibir_resultado_processamento(resultado)
        else:
            st.warning("⚠️ Por favor, faça o upload de uma planilha para limpar.")


# ==============================================================================
# FOOTER
# ==============================================================================

st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: #666; font-size: 0.875rem;'>"
    "Sistema de Planilhas Amazon v6.1 | Desenvolvido com Streamlit | "
    f"Atualizado em {datetime.now().strftime('%d/%m/%Y')}"
    "</div>",
    unsafe_allow_html=True
)
