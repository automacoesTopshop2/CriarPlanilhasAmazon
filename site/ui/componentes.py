# ==============================================================================
# COMPONENTES DE UI
# ==============================================================================
# Componentes de interface Streamlit reutilizáveis.
#
# Este módulo fornece:
#   - Containers de status com progresso
#   - Exibição de resultados de processamento
#   - Exibição de logs EM TEMPO REAL
#   - Botões de download
#   - Mensagens padronizadas
# ==============================================================================

import streamlit as st
import pandas as pd
import traceback
from typing import List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime

# Importação para tipagem
import sys
sys.path.insert(0, '..')
from core.utils import LogErro
from core.processadores.base import ResultadoProcessamento


class LogTempoReal:
    """
    Gerenciador de logs em tempo real para Streamlit.
    
    Usa containers st.empty() para atualizar logs dinamicamente
    durante o processamento.
    """
    
    def __init__(self, container):
        """
        Inicializa o gerenciador de logs.
        
        Args:
            container: Container Streamlit para os logs
        """
        self.container = container
        self.logs: List[str] = []
        self.max_logs = 50  # Máximo de logs a exibir
    
    def adicionar(self, mensagem: str, tipo: str = "info"):
        """
        Adiciona um log e atualiza a exibição.
        
        Args:
            mensagem: Texto do log
            tipo: Tipo (info, sucesso, erro, aviso)
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Ícone por tipo
        icones = {
            "info": "ℹ️",
            "sucesso": "✅",
            "erro": "❌",
            "aviso": "⚠️",
            "progresso": "⏳"
        }
        icone = icones.get(tipo, "•")
        
        log_formatado = f"`{timestamp}` {icone} {mensagem}"
        self.logs.append(log_formatado)
        
        # Mantém apenas os últimos N logs
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs:]
        
        # Atualiza exibição
        self._renderizar()
    
    def _renderizar(self):
        """Renderiza todos os logs no container."""
        with self.container:
            st.markdown("\n\n".join(self.logs))
    
    def limpar(self):
        """Limpa os logs."""
        self.logs.clear()
        with self.container:
            st.empty()


class ComponentesUI:
    """
    Classe com componentes de interface Streamlit reutilizáveis.
    
    Fornece métodos estáticos para criar elementos de UI padronizados
    como cards de status, exibição de erros, botões de download, etc.
    """
    
    # -------------------------------------------------------------------------
    # ESTILOS CSS CUSTOMIZADOS
    # -------------------------------------------------------------------------
    
    ESTILOS_CSS = """
    <style>
        /* Card de status */
        .status-card {
            padding: 1rem;
            border-radius: 0.5rem;
            margin-bottom: 1rem;
        }
        
        .status-sucesso {
            background-color: #d4edda;
            border: 1px solid #c3e6cb;
            color: #155724;
        }
        
        .status-erro {
            background-color: #f8d7da;
            border: 1px solid #f5c6cb;
            color: #721c24;
        }
        
        .status-aviso {
            background-color: #fff3cd;
            border: 1px solid #ffeeba;
            color: #856404;
        }
        
        /* Log container */
        .log-container {
            background-color: #1e1e1e;
            color: #d4d4d4;
            padding: 1rem;
            border-radius: 0.5rem;
            font-family: 'Consolas', 'Monaco', monospace;
            font-size: 0.85rem;
            max-height: 300px;
            overflow-y: auto;
        }
        
        /* Stat box melhorado */
        div[data-testid="metric-container"] {
            background-color: #f8f9fa;
            border: 1px solid #dee2e6;
            padding: 0.5rem;
            border-radius: 0.5rem;
        }
    </style>
    """
    
    @staticmethod
    def injetar_estilos():
        """Injeta os estilos CSS customizados na página."""
        st.markdown(ComponentesUI.ESTILOS_CSS, unsafe_allow_html=True)
    
    # -------------------------------------------------------------------------
    # PROCESSAMENTO COM LOGS EM TEMPO REAL
    # -------------------------------------------------------------------------
    
    @staticmethod
    def executar_com_logs_tempo_real(
        processador,
        arquivo_entrada,
        arquivo_template=None,
        titulo: str = "Processando..."
    ) -> Optional[ResultadoProcessamento]:
        """
        Executa o processamento com logs em tempo real.
        
        Args:
            processador: Instância do processador (SKU, ASIN, Limpeza)
            arquivo_entrada: Arquivo de entrada
            arquivo_template: Arquivo de template (opcional para limpeza)
            titulo: Título do processo
            
        Returns:
            ResultadoProcessamento ou None
        """
        # Container principal
        container_principal = st.container()
        
        with container_principal:
            # Header do processamento
            st.subheader(f"⚙️ {titulo}")
            
            # Barra de progresso
            barra_progresso = st.progress(0, text="Iniciando...")
            
            # Container para logs em tempo real
            st.markdown("**📋 Log de Execução:**")
            container_logs = st.empty()
            
            # Inicializa gerenciador de logs
            log_manager = LogTempoReal(container_logs)
        
        # Callbacks que atualizam em tempo real
        def callback_status(mensagem: str):
            """Callback para mensagens de status."""
            # Determina tipo baseado no conteúdo
            if "erro" in mensagem.lower() or "❌" in mensagem:
                tipo = "erro"
            elif "✅" in mensagem or "conclu" in mensagem.lower():
                tipo = "sucesso"
            elif "⚠" in mensagem or "aviso" in mensagem.lower():
                tipo = "aviso"
            else:
                tipo = "progresso"
            
            log_manager.adicionar(mensagem, tipo)
        
        def callback_progresso(valor: float):
            """Callback para atualização de progresso."""
            percentual = int(valor * 100)
            barra_progresso.progress(valor, text=f"Processando... {percentual}%")
        
        try:
            # Log inicial
            log_manager.adicionar("Iniciando processamento...", "info")
            
            # Executa o processamento
            resultado = processador.processar(
                arquivo_entrada=arquivo_entrada,
                arquivo_template=arquivo_template,
                callback_status=callback_status,
                callback_progresso=callback_progresso
            )
            
            # Log final
            if resultado.sucesso:
                log_manager.adicionar(
                    f"Processamento concluído! {resultado.total_processados} itens processados.",
                    "sucesso"
                )
                barra_progresso.progress(1.0, text="✅ Concluído!")
            else:
                log_manager.adicionar(f"Processamento falhou: {resultado.mensagem}", "erro")
                barra_progresso.progress(1.0, text="❌ Erro!")
            
            # Adiciona logs de erro/aviso do processador
            for log in resultado.logs:
                if log.tipo == "Erro":
                    log_manager.adicionar(f"[{log.sku}] {log.mensagem}", "erro")
                elif log.tipo == "Aviso":
                    log_manager.adicionar(f"[{log.sku}] {log.mensagem}", "aviso")
            
            return resultado
            
        except Exception as e:
            log_manager.adicionar(f"ERRO FATAL: {str(e)}", "erro")
            barra_progresso.progress(1.0, text="❌ Erro Fatal!")
            
            # Mostra traceback
            st.error(f"Erro durante processamento: {str(e)}")
            with st.expander("📋 Traceback Completo"):
                st.code(traceback.format_exc(), language="python")
            
            return None
    
    # -------------------------------------------------------------------------
    # EXIBIÇÃO DE RESULTADOS
    # -------------------------------------------------------------------------
    
    @staticmethod
    def exibir_resultado_processamento(resultado: ResultadoProcessamento):
        """
        Exibe o resultado de um processamento de forma visual.
        
        Args:
            resultado: Objeto ResultadoProcessamento
        """
        st.markdown("---")
        
        if resultado.sucesso:
            st.success(f"✅ {resultado.mensagem}")
            
            # Estatísticas em métricas
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    label="📊 Processados",
                    value=resultado.total_processados
                )
            
            with col2:
                st.metric(
                    label="❌ Erros",
                    value=resultado.total_erros,
                    delta=f"-{resultado.total_erros}" if resultado.total_erros > 0 else None,
                    delta_color="inverse"
                )
            
            with col3:
                st.metric(
                    label="⚠️ Avisos",
                    value=resultado.total_avisos
                )
            
            with col4:
                st.metric(
                    label="⏱️ Tempo",
                    value=f"{resultado.tempo_processamento:.1f}s"
                )
            
            st.markdown("---")
            
            # Botão de download destacado
            if resultado.arquivo_saida:
                col_download, col_info = st.columns([2, 1])
                
                with col_download:
                    st.download_button(
                        label="📥 BAIXAR PLANILHA PROCESSADA",
                        data=resultado.arquivo_saida.getvalue(),
                        file_name=resultado.nome_arquivo,
                        mime="application/vnd.ms-excel.sheet.macroEnabled.12",
                        type="primary",
                        use_container_width=True
                    )
                
                with col_info:
                    st.info(f"📄 {resultado.nome_arquivo}")
            
            # Logs detalhados em expander
            if resultado.logs:
                ComponentesUI.exibir_logs_detalhados(resultado.logs)
        
        else:
            st.error(f"❌ {resultado.mensagem}")
            
            # Mostra traceback se disponível
            for log in resultado.logs:
                if log.traceback:
                    with st.expander("🔍 Detalhes Técnicos do Erro"):
                        st.code(log.traceback, language="python")
            
            # Mostra todos os erros
            if resultado.logs:
                ComponentesUI.exibir_logs_detalhados(resultado.logs)
    
    @staticmethod
    def exibir_logs_detalhados(logs: List[LogErro], titulo: str = "📋 Detalhes do Processamento"):
        """
        Exibe logs detalhados em um expander com tabela.
        
        Args:
            logs: Lista de objetos LogErro
            titulo: Título do expander
        """
        if not logs:
            return
        
        # Conta por tipo
        erros = [l for l in logs if l.tipo == "Erro"]
        avisos = [l for l in logs if l.tipo == "Aviso"]
        
        # Resumo
        resumo_partes = []
        if erros:
            resumo_partes.append(f"❌ {len(erros)} erros")
        if avisos:
            resumo_partes.append(f"⚠️ {len(avisos)} avisos")
        
        if resumo_partes:
            st.warning(f"Encontrados: {', '.join(resumo_partes)}")
        
        # Tabela detalhada
        with st.expander(titulo, expanded=len(erros) > 0):
            # Cria DataFrame
            dados_tabela = []
            for log in logs:
                dados_tabela.append({
                    "⏱️ Hora": log.timestamp,
                    "🏷️ SKU": log.sku,
                    "📌 Tipo": f"{'❌' if log.tipo == 'Erro' else '⚠️' if log.tipo == 'Aviso' else 'ℹ️'} {log.tipo}",
                    "📝 Mensagem": log.mensagem
                })
            
            df = pd.DataFrame(dados_tabela)
            
            # Exibe tabela estilizada
            st.dataframe(
                df,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "⏱️ Hora": st.column_config.TextColumn(width="small"),
                    "🏷️ SKU": st.column_config.TextColumn(width="medium"),
                    "📌 Tipo": st.column_config.TextColumn(width="small"),
                    "📝 Mensagem": st.column_config.TextColumn(width="large"),
                }
            )
            
            # Opção de copiar logs
            if st.button("📋 Copiar Logs como Texto"):
                texto_logs = "\n".join([
                    f"{l.timestamp} | {l.tipo} | {l.sku} | {l.mensagem}"
                    for l in logs
                ])
                st.code(texto_logs, language="text")
    
    @staticmethod
    def exibir_logs(logs: List[LogErro], titulo: str = "Detalhes do Processamento"):
        """Wrapper para compatibilidade."""
        ComponentesUI.exibir_logs_detalhados(logs, titulo)
    
    # -------------------------------------------------------------------------
    # UPLOAD DE ARQUIVOS
    # -------------------------------------------------------------------------
    
    @staticmethod
    def upload_duplo(label1: str, label2: str, 
                    tipos1: List[str] = ["xlsx"],
                    tipos2: List[str] = ["xlsm"],
                    key_prefix: str = "") -> tuple:
        """
        Cria dois uploaders de arquivo lado a lado.
        
        Args:
            label1: Label do primeiro uploader
            label2: Label do segundo uploader
            tipos1: Tipos aceitos no primeiro
            tipos2: Tipos aceitos no segundo
            key_prefix: Prefixo para chaves únicas
            
        Returns:
            Tupla (arquivo1, arquivo2)
        """
        col1, col2 = st.columns(2)
        
        with col1:
            arquivo1 = st.file_uploader(
                label1, 
                type=tipos1,
                key=f"{key_prefix}_upload_1" if key_prefix else None
            )
        
        with col2:
            arquivo2 = st.file_uploader(
                label2, 
                type=tipos2,
                key=f"{key_prefix}_upload_2" if key_prefix else None
            )
        
        return arquivo1, arquivo2
    
    # -------------------------------------------------------------------------
    # PROCESSAMENTO LEGADO (mantido para compatibilidade)
    # -------------------------------------------------------------------------
    
    @staticmethod
    def processar_com_status(funcao_processamento: Callable,
                             titulo: str = "Processando...") -> Any:
        """
        DEPRECADO: Use executar_com_logs_tempo_real ao invés.
        Mantido para compatibilidade.
        """
        # Usa o novo método internamente
        try:
            return funcao_processamento(
                lambda msg: st.write(msg),
                lambda val: None
            )
        except Exception as e:
            st.error(f"Erro: {str(e)}")
            return None
    
    # -------------------------------------------------------------------------
    # MENSAGENS E ALERTAS
    # -------------------------------------------------------------------------
    
    @staticmethod
    def aviso_arquivos_faltando():
        """Exibe aviso padronizado quando arquivos não foram selecionados."""
        st.warning("⚠️ Por favor, faça o upload dos **dois arquivos** (Entrada e Modelo).")
    
    @staticmethod
    def aviso_bases_incompletas():
        """Exibe aviso quando as bases de dados não estão prontas."""
        st.warning(
            "⚠️ **Atenção**: As bases de dados não estão prontas.\n\n"
            "Use a barra lateral para:\n"
            "- 💰 Atualizar a base de **Precificação** (clique em 'Atualizar Precificação')\n"
            "- 📝 Fazer upload da base de **Descrição**"
        )
    
    @staticmethod
    def info_instrucoes(texto: str):
        """Exibe uma caixa de informações com instruções."""
        st.info(texto)
    
    # -------------------------------------------------------------------------
    # CARDS E CONTAINERS
    # -------------------------------------------------------------------------
    
    @staticmethod
    def card_categoria(titulo: str, descricao: str, icone: str = "📦"):
        """
        Exibe um card de categoria com ícone, título e descrição.
        
        Args:
            titulo: Título do card
            descricao: Descrição do card
            icone: Emoji ou ícone
        """
        st.markdown(f"""
        <div style="
            padding: 1rem;
            border-radius: 0.5rem;
            border: 1px solid #dee2e6;
            margin-bottom: 1rem;
            background-color: #f8f9fa;
        ">
            <h3>{icone} {titulo}</h3>
            <p style="color: #6c757d; margin: 0;">{descricao}</p>
        </div>
        """, unsafe_allow_html=True)
