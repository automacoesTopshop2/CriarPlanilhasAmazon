# ==============================================================================
# MAIN WINDOW - Janela principal do aplicativo desktop (modo dark)
# ==============================================================================
# Layout:
#   ┌─────────────────────────────────────────────────────────────┐
#   │  Sidebar     │            Conteúdo (view atual)              │
#   │  (nav)       │                                                │
#   └─────────────────────────────────────────────────────────────┘
# ==============================================================================

import customtkinter as ctk

from core.config import Configuracoes
from core.config_manager import GerenciadorConfig
from core.processadores import ProcessadorSKU, ProcessadorASIN, ProcessadorLimpeza

from .theme import Cores, Fontes
from .home_view import HomeView
from .settings_view import SettingsView
from .processing_view import ProcessingView
from .limpeza_view import TermosEditor


class MainWindow(ctk.CTk):
    """Janela principal."""

    LARGURA_MIN = 1100
    ALTURA_MIN = 740

    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title("Sistema de Planilhas Amazon")
        self.geometry(f"{self.LARGURA_MIN}x{self.ALTURA_MIN}")
        self.minsize(960, 640)
        self.configure(fg_color=Cores.APP_BG)

        # Estado
        self.gerenciador = GerenciadorConfig()
        self.config_app = Configuracoes()
        self.config_app.aplicar_gerenciador(self.gerenciador)

        # Layout
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._construir_sidebar()
        self._construir_container()

        # Views
        self._views: dict = {}
        self._botoes_nav: dict = {}
        self._construir_views()

        self._mostrar("home")

    # ---------------------------------------------------------------------
    # Sidebar
    # ---------------------------------------------------------------------

    def _construir_sidebar(self) -> None:
        self.sidebar = ctk.CTkFrame(self, width=240, corner_radius=0,
                                    fg_color=Cores.SIDEBAR_BG)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Logo / título
        logo = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        logo.pack(fill="x", padx=20, pady=(28, 16))

        ctk.CTkLabel(logo, text="📦", font=("Segoe UI", 32),
                     text_color=Cores.SIDEBAR_FG).pack(anchor="w")
        ctk.CTkLabel(logo, text="Planilhas Amazon",
                     font=("Segoe UI", 16, "bold"),
                     text_color=Cores.SIDEBAR_FG).pack(anchor="w")
        ctk.CTkLabel(logo, text="Versão Desktop 7.1",
                     font=Fontes.PEQUENA,
                     text_color=Cores.SIDEBAR_FG_MUTED).pack(anchor="w")

        # Separador
        sep = ctk.CTkFrame(self.sidebar, height=1, fg_color=Cores.BORDER)
        sep.pack(fill="x", padx=20, pady=(8, 0))

        # Navegação
        self.nav_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.nav_frame.pack(fill="x", padx=12, pady=(20, 0))

    def _add_nav(self, chave: str, texto: str, icone: str) -> None:
        botao = ctk.CTkButton(
            self.nav_frame,
            text=f"  {icone}   {texto}",
            font=Fontes.BOTAO, height=42, anchor="w",
            corner_radius=8,
            fg_color="transparent",
            hover_color=Cores.SIDEBAR_ACTIVE,
            text_color=Cores.SIDEBAR_FG,
            command=lambda: self._mostrar(chave),
        )
        botao.pack(fill="x", pady=3)
        self._botoes_nav[chave] = botao

    # ---------------------------------------------------------------------
    # Container
    # ---------------------------------------------------------------------

    def _construir_container(self) -> None:
        self.container = ctk.CTkFrame(self, fg_color=Cores.APP_BG, corner_radius=0)
        self.container.grid(row=0, column=1, sticky="nsew")
        self.container.grid_columnconfigure(0, weight=1)
        self.container.grid_rowconfigure(0, weight=1)

    # ---------------------------------------------------------------------
    # Views
    # ---------------------------------------------------------------------

    def _construir_views(self) -> None:
        # Botões de navegação na sidebar
        self._add_nav("home", "Início", "🏠")
        self._add_nav("sku", "Criar por SKU", "🏭")
        self._add_nav("asin", "Criar por ASIN", "⚡")
        self._add_nav("limpeza", "Limpeza", "🧹")
        self._add_nav("settings", "Configurações", "⚙️")

        # Home
        self._views["home"] = HomeView(
            self.container, self.config_app, self.gerenciador,
            ir_para=self._mostrar,
        )

        # SKU - aceita arquivo OU texto colado
        self._views["sku"] = ProcessingView(
            self.container, self.config_app,
            criar_processador=lambda: ProcessadorSKU(self.config_app),
            titulo="🏭 Criação via SKU",
            descricao=(
                "Use uma planilha de SKUs ou cole valores diretamente.\n"
                "Bases: Preços e Descrição. Saída: template NOGORA preenchido."
            ),
            precisa_template=True,
            filtros_entrada=[("Planilha SKU", "*.xlsx")],
            filtros_template=[("Template NOGORA", "*.xlsm")],
            colunas_texto=["SKU", "MARCA", "EAN"],
            placeholder_texto=(
                "Cole aqui — uma linha por SKU.\n"
                "Formato: SKU [TAB ou ;] MARCA [TAB ou ;] EAN\n\n"
                "Exemplos:\n"
                "NOGO-ABC123\tNogora\t7891234567890\n"
                "ATIV-XYZ789;Ativa;7890987654321\n"
                "BET-PROD01"
            ),
        )

        # ASIN - aceita arquivo OU texto colado
        self._views["asin"] = ProcessingView(
            self.container, self.config_app,
            criar_processador=lambda: ProcessadorASIN(self.config_app),
            titulo="⚡ Criação via ASIN",
            descricao=(
                "Use uma planilha de ASINs ou cole valores diretamente.\n"
                "Preenche apenas campos essenciais (preço, peso, medidas)."
            ),
            precisa_template=True,
            filtros_entrada=[("Planilha ASIN", "*.xlsx")],
            filtros_template=[("Template ListaASINS", "*.xlsm")],
            colunas_texto=["ASIN", "SKU"],
            placeholder_texto=(
                "Cole aqui — uma linha por ASIN.\n"
                "Formato: ASIN [TAB ou ;] SKU\n\n"
                "Exemplos:\n"
                "B0ABCDE123\tNOGO-ABC123\n"
                "B0XYZ12345;ATIV-XYZ789"
            ),
        )

        # Limpeza - sem texto, mas com editor de termos
        self._views["limpeza"] = ProcessingView(
            self.container, self.config_app,
            criar_processador=lambda: ProcessadorLimpeza(self.config_app),
            titulo="🧹 Limpeza de textos",
            descricao=(
                "Remove e substitui termos em planilhas com aba 'Modelo'.\n"
                "Gerencie os termos abaixo e depois selecione o arquivo a limpar."
            ),
            precisa_template=False,
            filtros_entrada=[("Planilhas Excel", "*.xlsx *.xlsm")],
            extra_widget_factory=lambda parent: TermosEditor(
                parent,
                processador_factory=lambda: ProcessadorLimpeza(self.config_app),
            ),
        )

        # Configurações
        self._views["settings"] = SettingsView(
            self.container, self.config_app, self.gerenciador,
            ao_salvar=self._reaplicar_config,
        )

    def _mostrar(self, chave: str) -> None:
        for nome, view in self._views.items():
            view.grid_forget()
        view_atual = self._views.get(chave)
        if view_atual is None:
            return
        view_atual.grid(row=0, column=0, sticky="nsew")

        for nome, botao in self._botoes_nav.items():
            if nome == chave:
                botao.configure(fg_color=Cores.SIDEBAR_HIGHLIGHT)
            else:
                botao.configure(fg_color="transparent")

        # Refresh do home a cada visita
        if chave == "home" and hasattr(view_atual, "atualizar_status"):
            view_atual.atualizar_status()

    # ---------------------------------------------------------------------
    # Reaplica config após salvar em Settings
    # ---------------------------------------------------------------------

    def _reaplicar_config(self) -> None:
        self.config_app = Configuracoes()
        self.config_app.aplicar_gerenciador(self.gerenciador)

        for nome, view in self._views.items():
            if hasattr(view, "config_app"):
                view.config_app = self.config_app

        if "home" in self._views:
            self._views["home"].atualizar_status()
