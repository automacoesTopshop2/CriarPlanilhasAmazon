# ==============================================================================
# PROCESSING VIEW - Tela genérica de processamento (SKU / ASIN / Limpeza)
# ==============================================================================
# - Suporta entrada via ARQUIVO ou TEXTO COLADO (quando colunas_texto é dado).
# - Aceita um widget extra acima da entrada (extra_widget_factory),
#   usado pelo módulo Limpeza para gerenciar termos.
# - Mostra logs em tempo real e barra de progresso.
# ==============================================================================

import io
import os
import threading
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk
import openpyxl

from .theme import Cores, Fontes


class ProcessingView(ctk.CTkFrame):
    """Tela genérica de execução de um processador."""

    def __init__(self, master, config_app, criar_processador,
                 titulo: str, descricao: str,
                 precisa_template: bool,
                 filtros_entrada: list,
                 filtros_template: list = None,
                 colunas_texto: list = None,
                 placeholder_texto: str = "",
                 extra_widget_factory=None):
        super().__init__(master, fg_color=Cores.APP_BG)
        self.config_app = config_app
        self.criar_processador = criar_processador
        self.titulo = titulo
        self.descricao = descricao
        self.precisa_template = precisa_template
        self.filtros_entrada = filtros_entrada
        self.filtros_template = filtros_template or []
        self.colunas_texto = colunas_texto or []
        self.placeholder_texto = placeholder_texto
        self.extra_widget_factory = extra_widget_factory

        self._caminho_entrada: str = ""
        self._caminho_template: str = ""
        self._resultado_arquivo = None
        self._nome_arquivo_saida: str = ""
        self._modo_atual: str = "arquivo"  # "arquivo" | "texto"

        self._construir()

    # ---------------------------------------------------------------------
    # Construção
    # ---------------------------------------------------------------------

    def _construir(self) -> None:
        self.scroll = ctk.CTkScrollableFrame(self, fg_color=Cores.APP_BG,
                                             scrollbar_button_color=Cores.BORDER_FORTE)
        self.scroll.pack(fill="both", expand=True)

        cab = ctk.CTkFrame(self.scroll, fg_color="transparent")
        cab.pack(fill="x", padx=32, pady=(28, 8))

        ctk.CTkLabel(cab, text=self.titulo, font=Fontes.TITULO, anchor="w").pack(anchor="w")
        ctk.CTkLabel(
            cab, text=self.descricao, font=Fontes.CORPO,
            text_color=Cores.TEXT_MUTED, anchor="w", justify="left",
        ).pack(anchor="w")

        # Widget extra (ex: editor de termos da Limpeza)
        if self.extra_widget_factory is not None:
            try:
                extra = self.extra_widget_factory(self.scroll)
                extra.pack(fill="x", padx=32, pady=(12, 0))
            except Exception as exc:
                ctk.CTkLabel(self.scroll, text=f"Erro no widget extra: {exc}",
                             text_color=Cores.DANGER).pack(padx=32, pady=8)

        # Bloco principal de entrada
        bloco = ctk.CTkFrame(self.scroll, corner_radius=12, border_width=1,
                             fg_color=Cores.CARD_BG, border_color=Cores.BORDER)
        bloco.pack(fill="x", padx=32, pady=(16, 8))

        # Toggle Arquivo / Texto (apenas se colunas_texto estiver definido)
        if self.colunas_texto:
            self._construir_toggle_modo(bloco)

        # Container que troca entre arquivo e texto
        self.container_entrada = ctk.CTkFrame(bloco, fg_color="transparent")
        self.container_entrada.pack(fill="x")

        # Seção: arquivo de entrada
        self.frame_arquivo = ctk.CTkFrame(self.container_entrada, fg_color="transparent")
        self.frame_arquivo.pack(fill="x")
        self.lbl_entrada = self._linha_arquivo(
            self.frame_arquivo, "Arquivo de entrada:",
            self._escolher_entrada, self.filtros_entrada,
        )

        # Seção: texto de entrada (oculta inicialmente)
        if self.colunas_texto:
            self.frame_texto = ctk.CTkFrame(self.container_entrada, fg_color="transparent")
            self._construir_modo_texto(self.frame_texto)
        else:
            self.frame_texto = None

        # Linha de template (se aplicável)
        if self.precisa_template:
            self.lbl_template = self._linha_arquivo(
                bloco, "Arquivo de template:",
                self._escolher_template, self.filtros_template,
            )
        else:
            self.lbl_template = None

        # Botões executar / salvar
        botoes = ctk.CTkFrame(bloco, fg_color="transparent")
        botoes.pack(fill="x", padx=16, pady=(4, 16))

        self.btn_executar = ctk.CTkButton(
            botoes, text="🚀 Executar processamento",
            font=Fontes.BOTAO, height=42,
            fg_color=Cores.PRIMARY, hover_color=Cores.PRIMARY_HOVER,
            command=self._executar,
        )
        self.btn_executar.pack(side="left", fill="x", expand=True)

        self.btn_salvar = ctk.CTkButton(
            botoes, text="💾 Salvar resultado",
            font=Fontes.BOTAO, height=42, width=180,
            fg_color=Cores.SUCCESS, hover_color=Cores.SUCCESS_HOVER,
            state="disabled", command=self._salvar_resultado,
        )
        self.btn_salvar.pack(side="right", padx=(8, 0))

        # Progresso
        self.barra = ctk.CTkProgressBar(self.scroll, height=14,
                                        progress_color=Cores.PRIMARY,
                                        fg_color=Cores.INPUT_BG)
        self.barra.set(0)
        self.barra.pack(fill="x", padx=32, pady=(8, 4))

        self.lbl_status = ctk.CTkLabel(self.scroll, text="Aguardando execução...",
                                       font=Fontes.CORPO, anchor="w",
                                       text_color=Cores.TEXT_MUTED)
        self.lbl_status.pack(fill="x", padx=32, pady=(0, 8))

        # Logs
        ctk.CTkLabel(self.scroll, text="Logs em tempo real",
                     font=Fontes.SECAO, anchor="w").pack(
            anchor="w", padx=32, pady=(8, 4)
        )

        self.txt_logs = ctk.CTkTextbox(
            self.scroll, font=Fontes.MONOESPACO, wrap="word", border_width=1,
            fg_color=Cores.INPUT_BG, border_color=Cores.BORDER,
            text_color=Cores.TEXT_PRIMARY, height=220,
        )
        self.txt_logs.pack(fill="both", expand=True, padx=32, pady=(0, 24))
        self.txt_logs.configure(state="disabled")

    # ---------------------------------------------------------------------
    # Toggle arquivo/texto
    # ---------------------------------------------------------------------

    def _construir_toggle_modo(self, parent) -> None:
        wrapper = ctk.CTkFrame(parent, fg_color="transparent")
        wrapper.pack(fill="x", padx=16, pady=(14, 0))

        ctk.CTkLabel(wrapper, text="Modo de entrada:",
                     font=Fontes.SECAO, anchor="w").pack(anchor="w")

        self.var_modo = ctk.StringVar(value="📁 Arquivo")
        self.seg_modo = ctk.CTkSegmentedButton(
            wrapper,
            values=["📁 Arquivo", "✍️ Digitar valores"],
            variable=self.var_modo,
            command=self._on_trocar_modo,
            fg_color=Cores.INPUT_BG,
            selected_color=Cores.PRIMARY,
            selected_hover_color=Cores.PRIMARY_HOVER,
            unselected_color=Cores.INPUT_BG,
            unselected_hover_color=Cores.HOVER_BG,
            height=34,
        )
        self.seg_modo.pack(fill="x", pady=(4, 0))

    def _on_trocar_modo(self, valor: str) -> None:
        if "Arquivo" in valor:
            self._modo_atual = "arquivo"
            if self.frame_texto:
                self.frame_texto.pack_forget()
            self.frame_arquivo.pack(fill="x")
        else:
            self._modo_atual = "texto"
            self.frame_arquivo.pack_forget()
            if self.frame_texto:
                self.frame_texto.pack(fill="x")

    # ---------------------------------------------------------------------
    # Modo TEXTO
    # ---------------------------------------------------------------------

    def _construir_modo_texto(self, parent) -> None:
        ctk.CTkLabel(parent, text=f"Colunas: {' / '.join(self.colunas_texto)}",
                     font=Fontes.SECAO, anchor="w").pack(anchor="w", padx=16, pady=(14, 0))

        ctk.CTkLabel(
            parent,
            text=("Cole uma linha por registro. Separe colunas com TAB (paste do Excel) ou ; ou ,. "
                  "Apenas a 1ª coluna é obrigatória."),
            font=Fontes.PEQUENA, text_color=Cores.TEXT_MUTED,
            anchor="w", justify="left", wraplength=900,
        ).pack(anchor="w", padx=16, pady=(2, 4))

        self.txt_entrada = ctk.CTkTextbox(
            parent, font=Fontes.MONOESPACO, height=160, wrap="none",
            fg_color=Cores.INPUT_BG, border_color=Cores.BORDER, border_width=1,
            text_color=Cores.TEXT_PRIMARY,
        )
        self.txt_entrada.pack(fill="x", padx=16, pady=(0, 8))

        if self.placeholder_texto:
            self.txt_entrada.insert("1.0", self.placeholder_texto)
            self.txt_entrada.bind("<FocusIn>", self._limpar_placeholder, add="+")
            self._tem_placeholder = True
        else:
            self._tem_placeholder = False

    def _limpar_placeholder(self, _evt=None) -> None:
        if getattr(self, "_tem_placeholder", False):
            conteudo = self.txt_entrada.get("1.0", "end-1c")
            if conteudo.strip() == self.placeholder_texto.strip():
                self.txt_entrada.delete("1.0", "end")
            self._tem_placeholder = False

    def _texto_para_workbook(self, texto: str) -> io.BytesIO:
        """Converte texto multi-linha em um BytesIO contendo um xlsx."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(self.colunas_texto)

        linhas_validas = 0
        for linha in texto.splitlines():
            linha = linha.strip()
            if not linha:
                continue
            if "\t" in linha:
                partes = linha.split("\t")
            elif ";" in linha:
                partes = linha.split(";")
            elif "," in linha:
                partes = linha.split(",")
            else:
                partes = [linha]
            partes = [p.strip() for p in partes]
            while len(partes) < len(self.colunas_texto):
                partes.append("")
            ws.append(partes[: len(self.colunas_texto)])
            linhas_validas += 1

        if linhas_validas == 0:
            raise ValueError("Nenhuma linha válida foi encontrada no texto.")

        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        return buffer

    # ---------------------------------------------------------------------
    # Linha "arquivo + procurar"
    # ---------------------------------------------------------------------

    def _linha_arquivo(self, parent, label, comando, filtros):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", padx=16, pady=(14, 0))

        ctk.CTkLabel(frame, text=label, font=Fontes.SECAO, anchor="w").pack(anchor="w")
        linha = ctk.CTkFrame(frame, fg_color="transparent")
        linha.pack(fill="x", pady=(4, 0))

        lbl = ctk.CTkLabel(
            linha, text="Nenhum arquivo selecionado.",
            font=Fontes.CORPO, text_color=Cores.TEXT_MUTED, anchor="w",
            fg_color=Cores.INPUT_BG, corner_radius=6, height=34,
        )
        lbl.pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            linha, text="Procurar...", font=Fontes.BOTAO,
            height=34, width=110,
            fg_color=Cores.HOVER_BG, hover_color=Cores.BORDER_FORTE,
            text_color=Cores.TEXT_PRIMARY, border_width=1, border_color=Cores.BORDER,
            command=lambda: comando(filtros),
        ).pack(side="right")

        return lbl

    # ---------------------------------------------------------------------
    # Seleção de arquivos
    # ---------------------------------------------------------------------

    def _escolher_entrada(self, filtros) -> None:
        caminho = filedialog.askopenfilename(title="Arquivo de entrada", filetypes=filtros)
        if caminho:
            self._caminho_entrada = caminho
            self.lbl_entrada.configure(
                text=f"✅ {os.path.basename(caminho)}",
                text_color=Cores.SUCCESS,
            )

    def _escolher_template(self, filtros) -> None:
        caminho = filedialog.askopenfilename(title="Arquivo de template", filetypes=filtros)
        if caminho:
            self._caminho_template = caminho
            self.lbl_template.configure(
                text=f"✅ {os.path.basename(caminho)}",
                text_color=Cores.SUCCESS,
            )

    # ---------------------------------------------------------------------
    # Execução
    # ---------------------------------------------------------------------

    def _resolver_entrada(self):
        """Retorna um caminho ou um BytesIO conforme o modo atual."""
        if self._modo_atual == "texto":
            texto = self.txt_entrada.get("1.0", "end-1c")
            if getattr(self, "_tem_placeholder", False) and texto.strip() == self.placeholder_texto.strip():
                texto = ""
            if not texto.strip():
                raise ValueError("O campo de texto está vazio.")
            return self._texto_para_workbook(texto)

        if not self._caminho_entrada:
            raise ValueError("Selecione o arquivo de entrada.")
        return self._caminho_entrada

    def _executar(self) -> None:
        try:
            entrada = self._resolver_entrada()
        except ValueError as exc:
            messagebox.showwarning("Atenção", str(exc))
            return

        if self.precisa_template and not self._caminho_template:
            messagebox.showwarning("Atenção", "Selecione o arquivo de template.")
            return

        self._limpar_logs()
        self._resultado_arquivo = None
        self.btn_executar.configure(state="disabled")
        self.btn_salvar.configure(state="disabled")
        self.barra.set(0)
        self._registrar(f"▶ Iniciando processamento em {datetime.now().strftime('%H:%M:%S')}")

        template = self._caminho_template if self.precisa_template else None

        def trabalhar():
            try:
                processador = self.criar_processador()

                def cb_status(msg: str):
                    self.after(0, lambda: self._registrar(msg))

                def cb_progresso(valor: float):
                    self.after(0, lambda: self.barra.set(min(max(valor, 0.0), 1.0)))

                resultado = processador.processar(
                    arquivo_entrada=entrada,
                    arquivo_template=template,
                    callback_status=cb_status,
                    callback_progresso=cb_progresso,
                )

                self.after(0, lambda: self._concluir(resultado))

            except Exception as exc:
                self.after(0, lambda: self._falhar(str(exc)))

        threading.Thread(target=trabalhar, daemon=True).start()

    def _concluir(self, resultado) -> None:
        self.btn_executar.configure(state="normal")
        self.barra.set(1.0 if resultado.sucesso else 0)

        cor = Cores.SUCCESS if resultado.sucesso else Cores.DANGER
        self.lbl_status.configure(text=resultado.mensagem, text_color=cor)
        self._registrar(resultado.mensagem)

        if resultado.logs:
            self._registrar("─" * 60)
            for log in resultado.logs[-50:]:
                self._registrar(f"[{log.tipo}] {log.sku}: {log.mensagem}")

        self._registrar(
            f"⏱ Tempo: {resultado.tempo_processamento:.2f}s | "
            f"Processados: {resultado.total_processados} | "
            f"Erros: {resultado.total_erros} | Avisos: {resultado.total_avisos}"
        )

        if resultado.sucesso and resultado.arquivo_saida:
            self._resultado_arquivo = resultado.arquivo_saida
            self._nome_arquivo_saida = resultado.nome_arquivo
            self.btn_salvar.configure(state="normal")

    def _falhar(self, mensagem: str) -> None:
        self.btn_executar.configure(state="normal")
        self.barra.set(0)
        self.lbl_status.configure(text=f"❌ Falha: {mensagem}", text_color=Cores.DANGER)
        self._registrar(f"❌ {mensagem}")

    # ---------------------------------------------------------------------
    # Salvar resultado
    # ---------------------------------------------------------------------

    def _salvar_resultado(self) -> None:
        if not self._resultado_arquivo:
            return

        ext = os.path.splitext(self._nome_arquivo_saida)[1] or ".xlsm"
        caminho = filedialog.asksaveasfilename(
            title="Salvar resultado",
            defaultextension=ext,
            initialfile=self._nome_arquivo_saida or "resultado.xlsm",
            filetypes=[("Planilha Excel com macros", "*.xlsm"),
                       ("Planilha Excel", "*.xlsx"),
                       ("Todos os arquivos", "*.*")],
        )
        if not caminho:
            return

        try:
            self._resultado_arquivo.seek(0)
            with open(caminho, "wb") as f:
                f.write(self._resultado_arquivo.read())
            self._resultado_arquivo.seek(0)
            messagebox.showinfo("Sucesso", f"Arquivo salvo em:\n{caminho}")
        except Exception as exc:
            messagebox.showerror("Erro", f"Falha ao salvar: {exc}")

    # ---------------------------------------------------------------------
    # Logs
    # ---------------------------------------------------------------------

    def _limpar_logs(self) -> None:
        self.txt_logs.configure(state="normal")
        self.txt_logs.delete("1.0", "end")
        self.txt_logs.configure(state="disabled")

    def _registrar(self, msg: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.txt_logs.configure(state="normal")
        self.txt_logs.insert("end", f"[{timestamp}] {msg}\n")
        self.txt_logs.see("end")
        self.txt_logs.configure(state="disabled")
        self.lbl_status.configure(text=msg, text_color=Cores.TEXT_MUTED)
