# ==============================================================================
# HOME VIEW - Tela inicial
# ==============================================================================
# Apresenta:
#   - Status das bases (Precificação / Descrição)
#   - Botão "Atualizar Precificação" (sincroniza do OneDrive)
#   - Botão "Atualizar Descrição" (manual: seleciona arquivo XLSX)
#   - Atalhos para os 3 módulos de processamento
# ==============================================================================

import os
import shutil
import threading
from datetime import datetime
from tkinter import filedialog

import customtkinter as ctk

from core.config import Configuracoes
from core.utils import Utilitarios
from .theme import Cores, Fontes


class HomeView(ctk.CTkFrame):
    """Tela inicial da aplicação."""

    def __init__(self, master, config: Configuracoes, gerenciador, ir_para):
        super().__init__(master, fg_color="transparent")
        self.config_app = config
        self.gerenciador = gerenciador
        self.ir_para = ir_para  # callback(nome_view)

        self._construir()
        self.atualizar_status()

    # ---------------------------------------------------------------------
    # Construção
    # ---------------------------------------------------------------------

    def _construir(self) -> None:
        # Cabeçalho
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=32, pady=(28, 12))

        ctk.CTkLabel(
            header,
            text="Sistema de Planilhas Amazon",
            font=Fontes.TITULO,
            anchor="w",
        ).pack(anchor="w")

        ctk.CTkLabel(
            header,
            text="Atualize as bases de dados e processe seus templates",
            font=Fontes.CORPO,
            text_color=Cores.MUTED,
            anchor="w",
        ).pack(anchor="w")

        # Cartões de bases
        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="x", padx=32, pady=(20, 12))
        cards.grid_columnconfigure((0, 1), weight=1, uniform="cards")

        self.card_preco = self._construir_card_base(
            cards,
            titulo="💰 Precificação",
            descricao="Sincroniza a planilha do OneDrive para uso local.",
            texto_botao="Atualizar Precificação",
            cor_botao=Cores.PRIMARY,
            cor_hover=Cores.PRIMARY_HOVER,
            comando=self._atualizar_precificacao,
        )
        self.card_preco["frame"].grid(row=0, column=0, padx=(0, 10), sticky="nsew")

        self.card_desc = self._construir_card_base(
            cards,
            titulo="📝 Descrição",
            descricao="Carregue manualmente o arquivo XLSX de descrição.",
            texto_botao="Atualizar Descrição",
            cor_botao=Cores.SUCCESS,
            cor_hover=Cores.SUCCESS_HOVER,
            comando=self._atualizar_descricao,
        )
        self.card_desc["frame"].grid(row=0, column=1, padx=(10, 0), sticky="nsew")

        # Atalhos para módulos
        atalhos = ctk.CTkFrame(self, fg_color="transparent")
        atalhos.pack(fill="x", padx=32, pady=(20, 12))

        ctk.CTkLabel(
            atalhos,
            text="Módulos de Processamento",
            font=Fontes.SUBTITULO,
            anchor="w",
        ).pack(anchor="w", pady=(0, 8))

        grid = ctk.CTkFrame(atalhos, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1, 2), weight=1, uniform="atalhos")

        self._construir_atalho(
            grid, 0, "🏭 Criar por SKU",
            "Gera template completo a partir de uma lista de SKUs.",
            lambda: self.ir_para("sku"),
        )
        self._construir_atalho(
            grid, 1, "⚡ Criar por ASIN",
            "Preenche template para ASINs já existentes.",
            lambda: self.ir_para("asin"),
        )
        self._construir_atalho(
            grid, 2, "🧹 Limpeza",
            "Remove e substitui termos em planilhas Amazon.",
            lambda: self.ir_para("limpeza"),
        )

        # Mensagens
        self.lbl_status = ctk.CTkLabel(self, text="", font=Fontes.CORPO, anchor="w")
        self.lbl_status.pack(fill="x", padx=32, pady=(8, 24))

    def _construir_card_base(self, parent, titulo, descricao, texto_botao,
                              cor_botao, cor_hover, comando):
        frame = ctk.CTkFrame(parent, corner_radius=14, border_width=1,
                             fg_color=Cores.CARD_BG, border_color=Cores.BORDER)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(frame, text=titulo, font=Fontes.SUBTITULO, anchor="w").grid(
            row=0, column=0, sticky="w", padx=20, pady=(18, 4)
        )
        ctk.CTkLabel(
            frame, text=descricao, font=Fontes.PEQUENA,
            text_color=Cores.MUTED, anchor="w", justify="left",
        ).grid(row=1, column=0, sticky="w", padx=20)

        lbl_status = ctk.CTkLabel(
            frame, text="Verificando...", font=Fontes.CORPO, anchor="w"
        )
        lbl_status.grid(row=2, column=0, sticky="w", padx=20, pady=(12, 0))

        lbl_data = ctk.CTkLabel(
            frame, text="", font=Fontes.PEQUENA,
            text_color=Cores.MUTED, anchor="w",
        )
        lbl_data.grid(row=3, column=0, sticky="w", padx=20)

        botao = ctk.CTkButton(
            frame, text=texto_botao, font=Fontes.BOTAO, height=38,
            fg_color=cor_botao, hover_color=cor_hover, command=comando,
        )
        botao.grid(row=4, column=0, sticky="ew", padx=20, pady=(16, 18))

        return {"frame": frame, "status": lbl_status, "data": lbl_data, "botao": botao}

    def _construir_atalho(self, parent, coluna, titulo, descricao, comando):
        card = ctk.CTkFrame(parent, corner_radius=12, border_width=1,
                            fg_color=Cores.CARD_BG, border_color=Cores.BORDER)
        card.grid(row=0, column=coluna, padx=6, sticky="nsew")

        ctk.CTkLabel(card, text=titulo, font=Fontes.SECAO, anchor="w").pack(
            anchor="w", padx=16, pady=(14, 4)
        )
        ctk.CTkLabel(
            card, text=descricao, font=Fontes.PEQUENA,
            text_color=Cores.MUTED, anchor="w", justify="left", wraplength=240,
        ).pack(anchor="w", padx=16)
        ctk.CTkButton(
            card, text="Abrir", font=Fontes.BOTAO, height=32,
            fg_color=Cores.INPUT_BG, border_width=1, border_color=Cores.BORDER,
            text_color=Cores.TEXT_PRIMARY, hover_color=Cores.HOVER_BG,
            command=comando,
        ).pack(fill="x", padx=16, pady=(12, 14))

    # ---------------------------------------------------------------------
    # Atualização de status
    # ---------------------------------------------------------------------

    def atualizar_status(self) -> None:
        self._atualizar_card(self.card_preco, self.config_app.arquivo_precificacao)
        self._atualizar_card(self.card_desc, self.config_app.arquivo_descricao)

    def _atualizar_card(self, card: dict, caminho: str) -> None:
        if os.path.exists(caminho):
            card["status"].configure(text="✅ Pronta", text_color=Cores.SUCCESS)
            try:
                mtime = os.path.getmtime(caminho)
                data = datetime.fromtimestamp(mtime).strftime("%d/%m/%Y %H:%M")
                card["data"].configure(text=f"Última atualização: {data}")
            except Exception:
                card["data"].configure(text="")
        else:
            card["status"].configure(text="❌ Ausente", text_color=Cores.DANGER)
            card["data"].configure(text=f"Arquivo esperado: {os.path.basename(caminho)}")

    # ---------------------------------------------------------------------
    # Ações
    # ---------------------------------------------------------------------

    def _info(self, msg: str, cor: str = Cores.MUTED) -> None:
        self.lbl_status.configure(text=msg, text_color=cor)

    def _atualizar_precificacao(self) -> None:
        self._info("⏳ Buscando precificação no OneDrive...")
        self.card_preco["botao"].configure(state="disabled")

        def trabalhar():
            try:
                sucesso, mensagem = Utilitarios.sincronizar_arquivo(
                    lista_origens=self.config_app.caminhos_precificacao_onedrive,
                    nome_destino_local=self.config_app.arquivo_precificacao,
                    nome_amigavel="Precificação",
                    usuario_home=self.config_app.usuario_home,
                )
            except Exception as exc:
                sucesso, mensagem = False, f"Erro: {exc}"

            def concluir():
                self.card_preco["botao"].configure(state="normal")
                self._info(mensagem, Cores.SUCCESS if sucesso else Cores.DANGER)
                self.atualizar_status()

            self.after(0, concluir)

        threading.Thread(target=trabalhar, daemon=True).start()

    def _atualizar_descricao(self) -> None:
        caminho = filedialog.askopenfilename(
            title="Selecione o arquivo de Descrição",
            filetypes=[("Planilhas Excel", "*.xlsx"), ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            return

        try:
            shutil.copy2(caminho, self.config_app.arquivo_descricao)
            self._info("✅ Base de Descrição atualizada!", Cores.SUCCESS)
            self.atualizar_status()
        except PermissionError:
            self._info(
                "⚠️ Sem permissão. Feche o arquivo de descrição e tente novamente.",
                Cores.DANGER,
            )
        except Exception as exc:
            self._info(f"❌ Erro ao copiar: {exc}", Cores.DANGER)
