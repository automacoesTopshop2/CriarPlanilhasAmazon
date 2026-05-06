# ==============================================================================
# SIDEBAR UI
# ==============================================================================
# Componente de barra lateral para gerenciamento de bases de dados.
#
# Este módulo fornece:
#   - Gerenciamento da base de Precificação (sincronização OneDrive)
#   - Gerenciamento da base de Descrição (upload manual)
#   - Navegação entre módulos
#   - Status das bases de dados
# ==============================================================================

import os
import time
import streamlit as st
from typing import Optional, Tuple

import sys
sys.path.insert(0, '..')
from core.config import Configuracoes
from core.utils import Utilitarios


class SidebarUI:
    """
    Gerencia a barra lateral da aplicação Streamlit.
    
    Fornece métodos para:
    - Exibir e gerenciar bases de dados
    - Navegação entre módulos
    - Sincronização com OneDrive
    """
    
    # Opções de menu disponíveis
    OPCOES_MENU = [
        "1. Criar por SKU",
        "2. Criar por ASIN", 
        "3. Limpeza"
    ]
    
    def __init__(self, config: Optional[Configuracoes] = None):
        """
        Inicializa o componente de sidebar.
        
        Args:
            config: Configurações do sistema (opcional)
        """
        self.config = config or Configuracoes()
    
    def renderizar(self) -> str:
        """
        Renderiza a barra lateral completa.
        
        Returns:
            Opção de menu selecionada
        """
        st.sidebar.title("📊 Bases de Dados")
        
        # Seção de Precificação
        self._renderizar_secao_precificacao()
        
        st.sidebar.markdown("---")
        
        # Seção de Descrição
        self._renderizar_secao_descricao()
        
        st.sidebar.markdown("---")
        
        # Menu de navegação
        menu_selecionado = st.sidebar.radio(
            "🔧 Selecione o Módulo:",
            self.OPCOES_MENU,
            label_visibility="visible"
        )
        
        # Informações do sistema
        self._renderizar_info_sistema()
        
        return menu_selecionado
    
    def _renderizar_secao_precificacao(self):
        """Renderiza a seção de gerenciamento de Precificação."""
        st.sidebar.subheader("💰 Precificação")
        
        # Status
        arquivo_existe = os.path.exists(self.config.arquivo_precificacao)
        status_texto = "✅ Pronta" if arquivo_existe else "❌ Ausente"
        status_cor = "green" if arquivo_existe else "red"
        
        st.sidebar.markdown(f"**Status:** <span style='color:{status_cor}'>{status_texto}</span>", 
                           unsafe_allow_html=True)
        
        if arquivo_existe:
            # Mostra data de modificação
            try:
                mtime = os.path.getmtime(self.config.arquivo_precificacao)
                from datetime import datetime
                data_mod = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
                st.sidebar.caption(f"Última atualização: {data_mod}")
            except Exception:
                pass
        
        # Botão de atualização
        if st.sidebar.button("🔄 Atualizar Precificação", use_container_width=True):
            with st.spinner("Buscando no OneDrive..."):
                sucesso, mensagem = Utilitarios.sincronizar_arquivo(
                    lista_origens=self.config.caminhos_precificacao_onedrive,
                    nome_destino_local=self.config.arquivo_precificacao,
                    nome_amigavel="Precificação",
                    usuario_home=self.config.usuario_home
                )
                
                if sucesso:
                    st.sidebar.success(mensagem)
                    time.sleep(1)
                    st.rerun()
                else:
                    st.sidebar.error(mensagem)
    
    def _renderizar_secao_descricao(self):
        """Renderiza a seção de gerenciamento de Descrição."""
        st.sidebar.subheader("📝 Descrição")
        
        # Status
        arquivo_existe = os.path.exists(self.config.arquivo_descricao)
        status_texto = "✅ Pronta" if arquivo_existe else "❌ Ausente"
        status_cor = "green" if arquivo_existe else "red"
        
        st.sidebar.markdown(f"**Status:** <span style='color:{status_cor}'>{status_texto}</span>", 
                           unsafe_allow_html=True)
        
        if arquivo_existe:
            try:
                mtime = os.path.getmtime(self.config.arquivo_descricao)
                from datetime import datetime
                data_mod = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
                st.sidebar.caption(f"Última atualização: {data_mod}")
            except Exception:
                pass
        
        # Upload de descrição
        arquivo_upload = st.sidebar.file_uploader(
            "Atualizar base de Descrição:",
            type=["xlsx"],
            key="upload_descricao"
        )
        
        if arquivo_upload:
            try:
                with open(self.config.arquivo_descricao, "wb") as f:
                    f.write(arquivo_upload.getbuffer())
                st.sidebar.success("✅ Base de Descrição atualizada!")
                time.sleep(0.5)
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Erro ao salvar: {e}")
    
    def _renderizar_info_sistema(self):
        """Renderiza informações do sistema."""
        st.sidebar.markdown("---")
        
        with st.sidebar.expander("ℹ️ Informações"):
            st.markdown("""
            **Sistema de Planilhas Amazon**  
            Versão: 6.0 (Refatorado)
            
            **Módulos disponíveis:**
            - **SKU**: Criação completa via lista de SKUs
            - **ASIN**: Vinculação rápida via ASINs
            - **Limpeza**: Higienização de textos
            
            **Suporte:**
            - Precificação: Sincronização via OneDrive
            - Descrição: Upload manual
            """)
    
    def verificar_bases_prontas(self) -> Tuple[bool, bool]:
        """
        Verifica se as bases de dados estão prontas.
        
        Returns:
            Tupla (precificacao_ok, descricao_ok)
        """
        preco_ok = os.path.exists(self.config.arquivo_precificacao)
        desc_ok = os.path.exists(self.config.arquivo_descricao)
        return preco_ok, desc_ok
    
    def todas_bases_prontas(self) -> bool:
        """
        Verifica se todas as bases necessárias estão prontas.
        
        Returns:
            True se ambas as bases existem
        """
        preco_ok, desc_ok = self.verificar_bases_prontas()
        return preco_ok and desc_ok
