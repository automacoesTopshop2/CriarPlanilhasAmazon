# ==============================================================================
# LIMPEZA VIEW - Editor de termos para o módulo de Limpeza
# ==============================================================================
# Apresenta dois painéis:
#   - "Termos para REMOVER": adiciona/edita/remove termos.
#   - "Termos para SUBSTITUIR": pares antigo => novo, mesma operação.
#
# As alterações são gravadas nos arquivos definidos no config
# (termos_remover.txt e termos_substituir.txt).
# ==============================================================================

import customtkinter as ctk
from tkinter import messagebox

from .theme import Cores, Fontes


class TermosEditor(ctk.CTkFrame):
    """Painel de gerenciamento de termos para o ProcessadorLimpeza."""

    def __init__(self, master, processador_factory):
        super().__init__(master, corner_radius=12, border_width=1,
                         fg_color=Cores.CARD_BG, border_color=Cores.BORDER)
        self.processador_factory = processador_factory

        self._linhas_remover = []   # cada item: {"frame", "entry"}
        self._linhas_substituir = []  # cada item: {"frame", "entry_a", "entry_b"}

        self._construir()
        self._carregar()

    # ---------------------------------------------------------------------
    # Construção
    # ---------------------------------------------------------------------

    def _construir(self) -> None:
        # Cabeçalho
        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", padx=16, pady=(14, 4))

        ctk.CTkLabel(cab, text="🛠 Editor de Termos de Limpeza",
                     font=Fontes.SUBTITULO, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            cab,
            text="Adicione, edite e remova termos. Clique em \"Salvar termos\" para persistir.",
            font=Fontes.PEQUENA, text_color=Cores.TEXT_MUTED,
            anchor="w", justify="left",
        ).pack(anchor="w")

        # Duas colunas
        colunas = ctk.CTkFrame(self, fg_color="transparent")
        colunas.pack(fill="x", padx=16, pady=(8, 4))
        colunas.grid_columnconfigure((0, 1), weight=1, uniform="termos")

        self._construir_coluna_remover(colunas).grid(row=0, column=0, padx=(0, 6), sticky="nsew")
        self._construir_coluna_substituir(colunas).grid(row=0, column=1, padx=(6, 0), sticky="nsew")

        # Barra de ações
        acoes = ctk.CTkFrame(self, fg_color="transparent")
        acoes.pack(fill="x", padx=16, pady=(6, 14))

        self.lbl_msg = ctk.CTkLabel(acoes, text="", font=Fontes.PEQUENA, anchor="w")
        self.lbl_msg.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            acoes, text="↻ Recarregar", font=Fontes.BOTAO,
            height=34, width=130,
            fg_color=Cores.HOVER_BG, hover_color=Cores.BORDER_FORTE,
            text_color=Cores.TEXT_PRIMARY, border_width=1, border_color=Cores.BORDER,
            command=self._carregar,
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            acoes, text="💾 Salvar termos", font=Fontes.BOTAO,
            height=34, width=160,
            fg_color=Cores.SUCCESS, hover_color=Cores.SUCCESS_HOVER,
            command=self._salvar,
        ).pack(side="right")

    def _construir_coluna_remover(self, parent) -> ctk.CTkFrame:
        col = ctk.CTkFrame(parent, fg_color=Cores.INPUT_BG, corner_radius=10,
                           border_width=1, border_color=Cores.BORDER)

        ctk.CTkLabel(col, text="🗑 Termos para REMOVER",
                     font=Fontes.SECAO, anchor="w").pack(
            anchor="w", padx=12, pady=(10, 0)
        )
        ctk.CTkLabel(
            col, text="Estes termos serão apagados do texto (case-insensitive).",
            font=Fontes.PEQUENA, text_color=Cores.TEXT_MUTED,
            anchor="w", justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self.scroll_remover = ctk.CTkScrollableFrame(
            col, fg_color="transparent", height=200,
            scrollbar_button_color=Cores.BORDER_FORTE,
        )
        self.scroll_remover.pack(fill="x", padx=8, pady=(0, 8))

        ctk.CTkButton(
            col, text="➕ Adicionar termo", font=Fontes.BOTAO,
            height=32,
            fg_color=Cores.PRIMARY, hover_color=Cores.PRIMARY_HOVER,
            command=lambda: self._add_linha_remover(""),
        ).pack(fill="x", padx=8, pady=(0, 12))

        return col

    def _construir_coluna_substituir(self, parent) -> ctk.CTkFrame:
        col = ctk.CTkFrame(parent, fg_color=Cores.INPUT_BG, corner_radius=10,
                           border_width=1, border_color=Cores.BORDER)

        ctk.CTkLabel(col, text="🔄 Termos para SUBSTITUIR",
                     font=Fontes.SECAO, anchor="w").pack(
            anchor="w", padx=12, pady=(10, 0)
        )
        ctk.CTkLabel(
            col, text="Cada par troca o termo antigo pelo novo (case-insensitive).",
            font=Fontes.PEQUENA, text_color=Cores.TEXT_MUTED,
            anchor="w", justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 4))

        # Cabeçalho de colunas
        cab = ctk.CTkFrame(col, fg_color="transparent")
        cab.pack(fill="x", padx=8, pady=(0, 4))
        cab.grid_columnconfigure((0, 1), weight=1, uniform="par")
        cab.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(cab, text="Antigo", font=Fontes.PEQUENA,
                     text_color=Cores.TEXT_MUTED, anchor="w").grid(
            row=0, column=0, sticky="w", padx=4
        )
        ctk.CTkLabel(cab, text="Novo", font=Fontes.PEQUENA,
                     text_color=Cores.TEXT_MUTED, anchor="w").grid(
            row=0, column=1, sticky="w", padx=4
        )

        self.scroll_substituir = ctk.CTkScrollableFrame(
            col, fg_color="transparent", height=200,
            scrollbar_button_color=Cores.BORDER_FORTE,
        )
        self.scroll_substituir.pack(fill="x", padx=8, pady=(0, 8))

        ctk.CTkButton(
            col, text="➕ Adicionar par", font=Fontes.BOTAO,
            height=32,
            fg_color=Cores.PRIMARY, hover_color=Cores.PRIMARY_HOVER,
            command=lambda: self._add_linha_substituir("", ""),
        ).pack(fill="x", padx=8, pady=(0, 12))

        return col

    # ---------------------------------------------------------------------
    # Linhas dinâmicas
    # ---------------------------------------------------------------------

    def _add_linha_remover(self, valor: str) -> None:
        linha = ctk.CTkFrame(self.scroll_remover, fg_color="transparent")
        linha.pack(fill="x", pady=2)

        entry = ctk.CTkEntry(
            linha, font=Fontes.CORPO, height=30,
            fg_color=Cores.CARD_BG, border_color=Cores.BORDER,
            text_color=Cores.TEXT_PRIMARY,
            placeholder_text="Termo a remover",
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        if valor:
            entry.insert(0, valor)

        registro = {"frame": linha, "entry": entry}

        def remover():
            try:
                self._linhas_remover.remove(registro)
            except ValueError:
                pass
            linha.destroy()

        ctk.CTkButton(
            linha, text="✕", width=30, height=30,
            font=Fontes.BOTAO,
            fg_color=Cores.DANGER, hover_color=Cores.DANGER_HOVER,
            command=remover,
        ).pack(side="right")

        self._linhas_remover.append(registro)

    def _add_linha_substituir(self, antigo: str, novo: str) -> None:
        linha = ctk.CTkFrame(self.scroll_substituir, fg_color="transparent")
        linha.pack(fill="x", pady=2)
        linha.grid_columnconfigure((0, 1), weight=1, uniform="par")
        linha.grid_columnconfigure(2, weight=0)

        e_ant = ctk.CTkEntry(
            linha, font=Fontes.CORPO, height=30,
            fg_color=Cores.CARD_BG, border_color=Cores.BORDER,
            text_color=Cores.TEXT_PRIMARY,
            placeholder_text="Antigo",
        )
        e_ant.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        if antigo:
            e_ant.insert(0, antigo)

        e_novo = ctk.CTkEntry(
            linha, font=Fontes.CORPO, height=30,
            fg_color=Cores.CARD_BG, border_color=Cores.BORDER,
            text_color=Cores.TEXT_PRIMARY,
            placeholder_text="Novo",
        )
        e_novo.grid(row=0, column=1, sticky="ew", padx=4)
        if novo:
            e_novo.insert(0, novo)

        registro = {"frame": linha, "entry_a": e_ant, "entry_b": e_novo}

        def remover():
            try:
                self._linhas_substituir.remove(registro)
            except ValueError:
                pass
            linha.destroy()

        ctk.CTkButton(
            linha, text="✕", width=30, height=30,
            font=Fontes.BOTAO,
            fg_color=Cores.DANGER, hover_color=Cores.DANGER_HOVER,
            command=remover,
        ).grid(row=0, column=2, padx=(4, 0))

        self._linhas_substituir.append(registro)

    # ---------------------------------------------------------------------
    # Carregar / Salvar
    # ---------------------------------------------------------------------

    def _carregar(self) -> None:
        # Limpa linhas existentes
        for reg in list(self._linhas_remover):
            reg["frame"].destroy()
        self._linhas_remover.clear()

        for reg in list(self._linhas_substituir):
            reg["frame"].destroy()
        self._linhas_substituir.clear()

        try:
            proc = self.processador_factory()
            termos_remover, termos_substituir = proc.carregar_termos()
        except Exception as exc:
            self._msg(f"❌ Falha ao carregar termos: {exc}", Cores.DANGER)
            return

        for termo in termos_remover:
            self._add_linha_remover(termo)

        for antigo, novo in termos_substituir.items():
            self._add_linha_substituir(antigo, novo)

        self._msg("✓ Termos carregados.", Cores.TEXT_MUTED)

    def _salvar(self) -> None:
        # Coleta termos a remover
        termos = []
        vistos = set()
        for reg in self._linhas_remover:
            valor = reg["entry"].get().strip()
            if not valor:
                continue
            chave = valor.lower()
            if chave in vistos:
                continue
            vistos.add(chave)
            termos.append(valor)

        # Coleta termos a substituir
        substituicoes = {}
        for reg in self._linhas_substituir:
            antigo = reg["entry_a"].get().strip()
            novo = reg["entry_b"].get()
            if not antigo:
                continue
            if antigo in substituicoes:
                messagebox.showerror(
                    "Substituição duplicada",
                    f"O termo antigo '{antigo}' aparece em mais de uma linha.",
                )
                return
            substituicoes[antigo] = novo

        try:
            proc = self.processador_factory()
            ok1 = proc.sobrescrever_termos_remover(termos)
            ok2 = proc.sobrescrever_termos_substituir(substituicoes)
        except Exception as exc:
            self._msg(f"❌ Erro: {exc}", Cores.DANGER)
            return

        if ok1 and ok2:
            self._msg(
                f"✅ Salvos: {len(termos)} para remover, {len(substituicoes)} substituições.",
                Cores.SUCCESS,
            )
        else:
            self._msg("⚠ Falha parcial ao salvar termos.", Cores.WARNING)

    def _msg(self, texto: str, cor: str) -> None:
        self.lbl_msg.configure(text=texto, text_color=cor)
        self.after(4000, lambda: self.lbl_msg.configure(text=""))
