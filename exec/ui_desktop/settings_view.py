# ==============================================================================
# SETTINGS VIEW - Tela de configurações
# ==============================================================================
# Permite editar:
#   - Caminho local do arquivo de Precificação
#   - Caminho local do arquivo de Descrição
#   - URL base de imagens
#   - Caminhos do OneDrive para sincronização (lista)
#   - Mapeamentos estáticos customizados (ADICIONAR / EDITAR / REMOVER)
# ==============================================================================

import os
from tkinter import filedialog, messagebox

import customtkinter as ctk

from .theme import Cores, Fontes


class SettingsView(ctk.CTkFrame):
    """Tela de configurações gerais e mapeamentos estáticos."""

    def __init__(self, master, config, gerenciador, ao_salvar):
        super().__init__(master, fg_color="transparent")
        self.config_app = config
        self.gerenciador = gerenciador
        self.ao_salvar = ao_salvar  # callback() para reaplicar config

        self._campos: dict = {}
        self._linhas_onedrive: list = []
        self._linhas_mapeamento: list = []

        self._construir()
        self._carregar_valores()

    # ---------------------------------------------------------------------
    # Construção
    # ---------------------------------------------------------------------

    def _construir(self) -> None:
        # Cabeçalho fixo
        cab = ctk.CTkFrame(self, fg_color="transparent")
        cab.pack(fill="x", padx=32, pady=(28, 8))

        ctk.CTkLabel(cab, text="Configurações", font=Fontes.TITULO, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            cab,
            text="Defina os caminhos das bases e os mapeamentos estáticos do template.",
            font=Fontes.CORPO, text_color=Cores.MUTED, anchor="w",
        ).pack(anchor="w")

        # Área scrollável
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.pack(fill="both", expand=True, padx=24, pady=(8, 8))

        self._construir_secao_arquivos(self.scroll)
        self._construir_secao_onedrive(self.scroll)
        self._construir_secao_mapeamentos(self.scroll)

        # Barra de ações
        rodape = ctk.CTkFrame(self, fg_color="transparent")
        rodape.pack(fill="x", padx=32, pady=(0, 24))

        self.lbl_msg = ctk.CTkLabel(rodape, text="", font=Fontes.CORPO, anchor="w")
        self.lbl_msg.pack(side="left")

        ctk.CTkButton(
            rodape, text="💾 Salvar Configurações", font=Fontes.BOTAO,
            height=40, width=200,
            fg_color=Cores.PRIMARY, hover_color=Cores.PRIMARY_HOVER,
            command=self._salvar,
        ).pack(side="right")

    # ----- arquivos locais -----

    def _construir_secao_arquivos(self, parent) -> None:
        secao = self._secao(parent, "📁 Arquivos das Bases de Dados")

        self._campo_arquivo(
            secao, "arquivo_precificacao",
            "Arquivo de Precificação (local):",
            "Selecione o XLSX onde a precificação ficará salva localmente.",
            [("Excel", "*.xlsx")],
        )
        self._campo_arquivo(
            secao, "arquivo_descricao",
            "Arquivo de Descrição (local):",
            "Selecione o XLSX usado como base de descrições.",
            [("Excel", "*.xlsx")],
        )
        self._campo_texto(
            secao, "url_base_imagens",
            "URL base das imagens:",
            "Ex: https://topshop-tiny.com.br/wp-content/uploads/tiny",
        )

    # ----- OneDrive -----

    def _construir_secao_onedrive(self, parent) -> None:
        secao = self._secao(
            parent, "☁️ Caminhos do OneDrive (Precificação)",
            descricao=(
                "Lista de caminhos onde o arquivo Precificacao Amazon.xlsx pode estar.\n"
                "Os caminhos relativos são combinados com a pasta do usuário automaticamente."
            ),
        )

        self.frame_onedrive = ctk.CTkFrame(secao, fg_color="transparent")
        self.frame_onedrive.pack(fill="x", padx=12, pady=(4, 8))

        ctk.CTkButton(
            secao, text="➕ Adicionar caminho",
            font=Fontes.BOTAO, height=34, width=200,
            command=lambda: self._add_linha_onedrive(""),
        ).pack(anchor="w", padx=12, pady=(4, 12))

    def _add_linha_onedrive(self, valor: str) -> None:
        linha = ctk.CTkFrame(self.frame_onedrive, fg_color="transparent")
        linha.pack(fill="x", pady=4)

        entry = ctk.CTkEntry(linha, font=Fontes.CORPO, height=34)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        if valor:
            entry.insert(0, valor)

        def remover():
            self._linhas_onedrive.remove(entry)
            linha.destroy()

        ctk.CTkButton(
            linha, text="✕", width=34, height=34,
            font=Fontes.BOTAO,
            fg_color=Cores.DANGER, hover_color=Cores.DANGER_HOVER,
            command=remover,
        ).pack(side="right")

        self._linhas_onedrive.append(entry)

    # ----- mapeamentos estáticos -----

    def _construir_secao_mapeamentos(self, parent) -> None:
        secao = self._secao(
            parent, "🏷️ Mapeamentos Estáticos Customizados",
            descricao=(
                "Adicione colunas que devem ser preenchidas com um valor fixo no template.\n"
                "Estas entradas se somam (e sobrescrevem) os valores padrão do sistema."
            ),
        )

        # Cabeçalho da tabela
        cab = ctk.CTkFrame(secao, fg_color=Cores.INPUT_BG, corner_radius=6)
        cab.pack(fill="x", padx=12)
        cab.grid_columnconfigure(0, weight=2)
        cab.grid_columnconfigure(1, weight=3)
        cab.grid_columnconfigure(2, weight=0)

        ctk.CTkLabel(cab, text="Nome da coluna", font=Fontes.SECAO, anchor="w").grid(
            row=0, column=0, sticky="w", padx=10, pady=8
        )
        ctk.CTkLabel(cab, text="Valor fixo", font=Fontes.SECAO, anchor="w").grid(
            row=0, column=1, sticky="w", padx=10, pady=8
        )

        self.frame_mapas = ctk.CTkFrame(secao, fg_color="transparent")
        self.frame_mapas.pack(fill="x", padx=12, pady=(2, 8))

        ctk.CTkButton(
            secao, text="➕ Adicionar valor de mapeamento estático",
            font=Fontes.BOTAO, height=36, width=300,
            fg_color=Cores.SUCCESS, hover_color=Cores.SUCCESS_HOVER,
            command=lambda: self._add_linha_mapeamento("", ""),
        ).pack(anchor="w", padx=12, pady=(4, 12))

    def _add_linha_mapeamento(self, nome: str, valor: str) -> None:
        linha = ctk.CTkFrame(self.frame_mapas, fg_color="transparent")
        linha.pack(fill="x", pady=4)
        linha.grid_columnconfigure(0, weight=2)
        linha.grid_columnconfigure(1, weight=3)
        linha.grid_columnconfigure(2, weight=0)

        e_nome = ctk.CTkEntry(linha, font=Fontes.CORPO, height=34,
                              placeholder_text="Ex: Ação de oferta")
        e_nome.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        if nome:
            e_nome.insert(0, nome)

        e_valor = ctk.CTkEntry(linha, font=Fontes.CORPO, height=34,
                               placeholder_text="Ex: Criar ou substituir...")
        e_valor.grid(row=0, column=1, sticky="ew", padx=6)
        if valor:
            e_valor.insert(0, valor)

        registro = {"nome": e_nome, "valor": e_valor, "frame": linha}

        def remover():
            self._linhas_mapeamento.remove(registro)
            linha.destroy()

        ctk.CTkButton(
            linha, text="✕", width=34, height=34,
            font=Fontes.BOTAO,
            fg_color=Cores.DANGER, hover_color=Cores.DANGER_HOVER,
            command=remover,
        ).grid(row=0, column=2, padx=(6, 0))

        self._linhas_mapeamento.append(registro)

    # ---------------------------------------------------------------------
    # Helpers de UI genéricos
    # ---------------------------------------------------------------------

    def _secao(self, parent, titulo: str, descricao: str = "") -> ctk.CTkFrame:
        bloco = ctk.CTkFrame(parent, corner_radius=12, border_width=1,
                             fg_color=Cores.CARD_BG, border_color=Cores.BORDER)
        bloco.pack(fill="x", padx=8, pady=(12, 8))

        ctk.CTkLabel(bloco, text=titulo, font=Fontes.SUBTITULO, anchor="w").pack(
            anchor="w", padx=16, pady=(14, 0)
        )
        if descricao:
            ctk.CTkLabel(
                bloco, text=descricao, font=Fontes.PEQUENA,
                text_color=Cores.MUTED, anchor="w", justify="left",
            ).pack(anchor="w", padx=16, pady=(2, 8))
        else:
            ctk.CTkLabel(bloco, text="").pack(pady=2)

        return bloco

    def _campo_texto(self, parent, chave: str, label: str, placeholder: str) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=12, pady=6)

        ctk.CTkLabel(frame, text=label, font=Fontes.SECAO, anchor="w").pack(anchor="w")
        entry = ctk.CTkEntry(frame, font=Fontes.CORPO, height=34, placeholder_text=placeholder)
        entry.pack(fill="x", pady=(4, 0))

        self._campos[chave] = entry

    def _campo_arquivo(self, parent, chave: str, label: str,
                       descricao: str, filtros: list) -> None:
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=12, pady=6)

        ctk.CTkLabel(frame, text=label, font=Fontes.SECAO, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            frame, text=descricao, font=Fontes.PEQUENA,
            text_color=Cores.MUTED, anchor="w",
        ).pack(anchor="w")

        linha = ctk.CTkFrame(frame, fg_color="transparent")
        linha.pack(fill="x", pady=(4, 0))

        entry = ctk.CTkEntry(linha, font=Fontes.CORPO, height=34)
        entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        def escolher():
            caminho = filedialog.askopenfilename(title=label, filetypes=filtros)
            if caminho:
                entry.delete(0, "end")
                entry.insert(0, caminho)

        ctk.CTkButton(
            linha, text="Procurar...", font=Fontes.BOTAO,
            height=34, width=110, command=escolher,
        ).pack(side="right")

        self._campos[chave] = entry

    # ---------------------------------------------------------------------
    # Carregar / Salvar
    # ---------------------------------------------------------------------

    def _carregar_valores(self) -> None:
        for chave, entry in self._campos.items():
            entry.delete(0, "end")
            entry.insert(0, str(self.gerenciador.get(chave, "")))

        # OneDrive
        for entry in list(self._linhas_onedrive):
            entry.master.destroy()
        self._linhas_onedrive.clear()
        for caminho in self.gerenciador.caminhos_onedrive():
            self._add_linha_onedrive(caminho)
        if not self._linhas_onedrive:
            self._add_linha_onedrive("")

        # Mapeamentos
        for reg in list(self._linhas_mapeamento):
            reg["frame"].destroy()
        self._linhas_mapeamento.clear()
        for nome, valor in self.gerenciador.valores_fixos_customizados().items():
            self._add_linha_mapeamento(nome, str(valor))

    def _salvar(self) -> None:
        # Campos simples
        for chave, entry in self._campos.items():
            self.gerenciador.dados[chave] = entry.get().strip()

        # OneDrive
        caminhos = [e.get().strip() for e in self._linhas_onedrive if e.get().strip()]
        self.gerenciador.dados["caminhos_precificacao_onedrive"] = caminhos

        # Mapeamentos (validação contra duplicatas)
        novos = {}
        for reg in self._linhas_mapeamento:
            nome = reg["nome"].get().strip()
            valor = reg["valor"].get()
            if not nome:
                continue
            if nome in novos:
                messagebox.showerror(
                    "Mapeamento duplicado",
                    f"A coluna '{nome}' está duplicada na lista de mapeamentos.",
                )
                return
            novos[nome] = valor
        self.gerenciador.dados["valores_fixos_customizados"] = novos

        try:
            self.gerenciador.salvar()
        except Exception as exc:
            messagebox.showerror("Erro ao salvar", str(exc))
            return

        if self.ao_salvar:
            self.ao_salvar()

        self.lbl_msg.configure(text="✅ Configurações salvas.", text_color=Cores.SUCCESS)
        self.after(2500, lambda: self.lbl_msg.configure(text=""))
