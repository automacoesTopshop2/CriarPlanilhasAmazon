# ==============================================================================
# GERENCIADOR DE CONFIGURAÇÕES (JSON)
# ==============================================================================
# Persiste e carrega configurações editáveis via UI em um arquivo JSON.
# Substitui o uso direto do .env, permitindo que o usuário edite tudo
# pela tela de Configurações da aplicação desktop.
#
# A configuração é armazenada em:
#   - Diretório do executável (modo portable), ou
#   - %APPDATA%/CriarPlanilhasAmazon/config.json (modo instalado)
#
# Estrutura do JSON:
#   {
#     "arquivo_precificacao": "caminho/local.xlsx",
#     "arquivo_descricao":    "caminho/local.xlsx",
#     "url_base_imagens":     "https://...",
#     "caminhos_precificacao_onedrive": ["...", "..."],
#     "valores_fixos_customizados": {"Coluna X": "Valor", ...}
#   }
# ==============================================================================

import os
import sys
import json
from typing import Dict, List, Any, Optional
from pathlib import Path


class GerenciadorConfig:
    """
    Gerencia o arquivo de configuração persistido em JSON.

    Permite que toda a configuração (caminhos, mapeamentos estáticos
    customizados, URL de imagens) seja editada via UI e persistida
    entre execuções.
    """

    NOME_ARQUIVO = "app_config.json"
    PASTA_APPDATA = "CriarPlanilhasAmazon"

    PADROES: Dict[str, Any] = {
        "arquivo_precificacao": "Precificacao.xlsx",
        # Modalidade FULL (isolada): base de preço própria + NCM (Drop-estoque)
        "arquivo_precificacao_full": "Precificacao Amazon - Full.xlsx",
        "aba_precificacao_full": "CLA",
        "arquivo_drop_estoque": "Drop estoque.xlsx",
        "arquivo_descricao": "DESCRIÇÃO.xlsx",
        "arquivo_remover": "termos_remover.txt",
        "arquivo_substituir": "termos_substituir.txt",
        "url_base_imagens": "https://topshop-tiny.com.br/wp-content/uploads/tiny",
        "caminhos_precificacao_onedrive": [
            r"OneDrive - Top Shop\Criação de Anúncios - Documentos\Precificacao Amazon.xlsx",
            r"OneDrive\Criação de Anúncios - Documentos\Precificacao Amazon.xlsx",
        ],
        "valores_fixos_customizados": {},
        "valores_fixos_excluidos": [],
        # SharePoint — link de compartilhamento direto (credenciais em env vars)
        "sharepoint_link_precificacao": "",
        "sharepoint_link_precificacao_full": "",   # aba CLA da Precificação Full
        "sharepoint_link_drop_estoque": "",        # NCM (sempre o xlsx "... - Drop estoque")
        "sharepoint_sync_no_startup": True,
        # Mapas editáveis via UI admin (vazio = usa default de config.py)
        "mapa_colunas_descricao": {},      # { "sku": ["SKU", ...], "titulo": [...], ... }
        "mapa_colunas_excluidos": [],      # chaves inteiras removidas via painel
        "mapa_prefixo_conta": {},          # { "NOGO-": "Nogora", ... }
        "prefixos_excluidos": [],          # prefixos removidos via painel
        "mapa_colunas_precificacao": {},   # { "sku": ["SKU", ...], "preco_padrao": [...] }
        "mapa_precificacao_excluidos": [], # chaves inteiras removidas via painel
    }

    def __init__(self, caminho_arquivo: Optional[str] = None):
        self.caminho_arquivo = caminho_arquivo or self._descobrir_caminho()
        self.dados: Dict[str, Any] = {}
        self.carregar()

    # ---------------------------------------------------------------------
    # Localização do arquivo
    # ---------------------------------------------------------------------

    def _descobrir_caminho(self) -> str:
        """Define onde gravar o JSON.

        Prioridade:
          1. ``APP_CONFIG_PATH`` no ambiente — override explícito.
          2. ``DATA_DIR`` (Railway/Docker) — grava em ``$DATA_DIR/app_config.json``,
             que aponta para o volume persistente. Sem isso o JSON cai em
             ``/app`` (filesystem efêmero do container) e é perdido a cada
             redeploy/restart, fazendo edições "voltarem" para o default.
          3. Quando empacotado em .exe via PyInstaller, grava ao lado do
             executável (modo portable).
          4. Caso contrário, grava na raiz do projeto (desenvolvimento).
        """
        env_path = os.getenv("APP_CONFIG_PATH", "").strip()
        if env_path:
            return env_path

        data_dir = os.getenv("DATA_DIR", "").strip()
        if data_dir:
            return str(Path(data_dir) / self.NOME_ARQUIVO)

        if getattr(sys, "frozen", False):
            base = Path(sys.executable).parent
        else:
            base = Path(__file__).resolve().parent.parent

        return str(base / self.NOME_ARQUIVO)

    # ---------------------------------------------------------------------
    # Persistência
    # ---------------------------------------------------------------------

    def carregar(self) -> None:
        """Lê o JSON do disco; se não existir, usa padrões e cria."""
        if os.path.exists(self.caminho_arquivo):
            try:
                with open(self.caminho_arquivo, "r", encoding="utf-8") as f:
                    self.dados = json.load(f)
            except Exception:
                self.dados = {}
        else:
            self.dados = {}

        # Garante todas as chaves padrão
        alterado = False
        for chave, valor in self.PADROES.items():
            if chave not in self.dados:
                self.dados[chave] = json.loads(json.dumps(valor))
                alterado = True

        if alterado or not os.path.exists(self.caminho_arquivo):
            self.salvar()

    def salvar(self) -> None:
        """Persiste o JSON em disco com indentação."""
        try:
            os.makedirs(os.path.dirname(self.caminho_arquivo) or ".", exist_ok=True)
        except Exception:
            pass

        with open(self.caminho_arquivo, "w", encoding="utf-8") as f:
            json.dump(self.dados, f, indent=2, ensure_ascii=False)

    # ---------------------------------------------------------------------
    # Acesso / mutação
    # ---------------------------------------------------------------------

    def get(self, chave: str, padrao: Any = None) -> Any:
        return self.dados.get(chave, padrao if padrao is not None else self.PADROES.get(chave))

    def set(self, chave: str, valor: Any) -> None:
        self.dados[chave] = valor
        self.salvar()

    # ---- caminhos OneDrive ----

    def caminhos_onedrive(self) -> List[str]:
        valor = self.dados.get("caminhos_precificacao_onedrive", [])
        return [c for c in valor if c and c.strip()]

    def definir_caminhos_onedrive(self, caminhos: List[str]) -> None:
        self.set("caminhos_precificacao_onedrive", [c.strip() for c in caminhos if c and c.strip()])

    # ---- mapeamentos estáticos customizados ----

    def valores_fixos_customizados(self) -> Dict[str, str]:
        return dict(self.dados.get("valores_fixos_customizados", {}))

    def adicionar_valor_fixo(self, nome_coluna: str, valor: str) -> None:
        nome_coluna = nome_coluna.strip()
        if not nome_coluna:
            return
        atuais = self.valores_fixos_customizados()
        atuais[nome_coluna] = valor
        self.set("valores_fixos_customizados", atuais)

    def atualizar_valor_fixo(self, nome_antigo: str, nome_novo: str, valor: str) -> None:
        nome_novo = nome_novo.strip()
        atuais = self.valores_fixos_customizados()
        if nome_antigo in atuais:
            del atuais[nome_antigo]
        elif nome_antigo != nome_novo:
            # Item hardcoded sendo renomeado: exclui o nome antigo
            excluidos = list(self.dados.get("valores_fixos_excluidos", []))
            if nome_antigo not in excluidos:
                excluidos.append(nome_antigo)
                self.dados["valores_fixos_excluidos"] = excluidos
        if nome_novo:
            atuais[nome_novo] = valor
        self.set("valores_fixos_customizados", atuais)

    def remover_valor_fixo(self, nome_coluna: str) -> None:
        atuais = self.valores_fixos_customizados()
        if nome_coluna in atuais:
            del atuais[nome_coluna]
            self.set("valores_fixos_customizados", atuais)
        else:
            # Item hardcoded: registra na lista de exclusões
            excluidos = list(self.dados.get("valores_fixos_excluidos", []))
            if nome_coluna not in excluidos:
                excluidos.append(nome_coluna)
                self.set("valores_fixos_excluidos", excluidos)

    # ---- helpers: inicialização a partir do estado efetivo ----
    # Garantem que o JSON contém o estado completo (hardcoded + overrides)
    # antes de qualquer remoção, para que o item hardcoded fique visível
    # ao método de remoção que só lê o JSON.

    def inicializar_mapa_colunas_de_efetivo(self, efetivo: Dict[str, List[str]]) -> None:
        atual = self.mapa_colunas_descricao()
        completo = {k: list(v) for k, v in efetivo.items()}
        completo.update(atual)  # preserva overrides já salvos
        self.definir_mapa_colunas(completo)

    def inicializar_mapa_prefixo_de_efetivo(self, efetivo: Dict[str, str]) -> None:
        atual = self.mapa_prefixo_conta()
        completo = dict(efetivo)
        completo.update(atual)
        self.definir_mapa_prefixo(completo)

    def inicializar_mapa_precificacao_de_efetivo(self, efetivo: Dict[str, List[str]]) -> None:
        atual = self.mapa_colunas_precificacao()
        completo = {k: list(v) for k, v in efetivo.items()}
        completo.update(atual)
        self.definir_mapa_colunas_precificacao(completo)

    # ---- mapa_colunas_descricao ----

    def mapa_colunas_descricao(self) -> Dict[str, List[str]]:
        return dict(self.dados.get("mapa_colunas_descricao", {}))

    def definir_mapa_colunas(self, mapa: Dict[str, List[str]]) -> None:
        limpo = {
            (k or "").strip(): [s.strip() for s in (v or []) if s and s.strip()]
            for k, v in (mapa or {}).items()
            if k and k.strip()
        }
        self.set("mapa_colunas_descricao", limpo)

    def adicionar_sinonimo_coluna(self, chave_logica: str, sinonimo: str) -> None:
        chave = (chave_logica or "").strip()
        sinonimo = (sinonimo or "").strip()
        if not chave or not sinonimo:
            return
        atual = self.mapa_colunas_descricao()
        lista = list(atual.get(chave, []))
        if sinonimo not in lista:
            lista.append(sinonimo)
        atual[chave] = lista
        self.definir_mapa_colunas(atual)

    def remover_sinonimo_coluna(self, chave_logica: str, sinonimo: str) -> None:
        atual = self.mapa_colunas_descricao()
        if chave_logica in atual:
            atual[chave_logica] = [s for s in atual[chave_logica] if s != sinonimo]
            self.definir_mapa_colunas(atual)

    def remover_chave_coluna(self, chave_logica: str) -> None:
        atual = self.mapa_colunas_descricao()
        if chave_logica in atual:
            del atual[chave_logica]
            self.definir_mapa_colunas(atual)
        excluidos = list(self.dados.get("mapa_colunas_excluidos", []))
        if chave_logica not in excluidos:
            excluidos.append(chave_logica)
            self.set("mapa_colunas_excluidos", excluidos)

    # ---- mapa_prefixo_conta ----

    def mapa_prefixo_conta(self) -> Dict[str, str]:
        return dict(self.dados.get("mapa_prefixo_conta", {}))

    def definir_mapa_prefixo(self, mapa: Dict[str, str]) -> None:
        limpo = {
            (k or "").strip().upper(): (v or "").strip()
            for k, v in (mapa or {}).items()
            if k and k.strip() and v and v.strip()
        }
        self.set("mapa_prefixo_conta", limpo)

    def adicionar_prefixo(self, prefixo: str, conta: str) -> None:
        prefixo = (prefixo or "").strip().upper()
        conta = (conta or "").strip()
        if not prefixo or not conta:
            return
        if not prefixo.endswith("-"):
            prefixo = prefixo + "-"
        atual = self.mapa_prefixo_conta()
        atual[prefixo] = conta
        self.definir_mapa_prefixo(atual)
        # Remove da lista de exclusões caso tenha sido deletado antes
        excluidos = [p for p in self.dados.get("prefixos_excluidos", []) if p != prefixo]
        self.dados["prefixos_excluidos"] = excluidos
        self.salvar()

    def remover_prefixo(self, prefixo: str) -> None:
        atual = self.mapa_prefixo_conta()
        if prefixo in atual:
            del atual[prefixo]
            self.definir_mapa_prefixo(atual)
        excluidos = list(self.dados.get("prefixos_excluidos", []))
        if prefixo not in excluidos:
            excluidos.append(prefixo)
            self.set("prefixos_excluidos", excluidos)

    def atualizar_prefixo(self, prefixo_antigo: str, prefixo_novo: str, conta: str) -> None:  # noqa: E501
        """
        Atualiza um prefixo existente. Se `prefixo_novo` for diferente de
        `prefixo_antigo`, remove a entrada antiga e cria a nova.

        Funciona tanto para prefixos customizados quanto para padrão:
        editar um padrão cria um override no JSON com o mesmo (ou novo) nome.
        """
        prefixo_antigo = (prefixo_antigo or "").strip().upper()
        prefixo_novo = (prefixo_novo or "").strip().upper()
        conta = (conta or "").strip()
        if not prefixo_novo or not conta:
            return
        if not prefixo_novo.endswith("-"):
            prefixo_novo = prefixo_novo + "-"
        atual = self.mapa_prefixo_conta()
        if prefixo_antigo and prefixo_antigo != prefixo_novo and prefixo_antigo in atual:
            del atual[prefixo_antigo]
        atual[prefixo_novo] = conta
        self.definir_mapa_prefixo(atual)
        # Se o antigo foi excluído antes, mantém exclusão; remove o novo das exclusões
        excluidos = list(self.dados.get("prefixos_excluidos", []))
        if prefixo_antigo and prefixo_antigo != prefixo_novo and prefixo_antigo not in excluidos:
            excluidos.append(prefixo_antigo)
        excluidos = [p for p in excluidos if p != prefixo_novo]
        self.dados["prefixos_excluidos"] = excluidos
        self.salvar()

    # ---- mapa_colunas_precificacao ----

    def mapa_colunas_precificacao(self) -> Dict[str, List[str]]:
        return dict(self.dados.get("mapa_colunas_precificacao", {}))

    def definir_mapa_colunas_precificacao(self, mapa: Dict[str, List[str]]) -> None:
        limpo = {
            (k or "").strip(): [s.strip() for s in (v or []) if s and s.strip()]
            for k, v in (mapa or {}).items()
            if k and k.strip()
        }
        self.set("mapa_colunas_precificacao", limpo)

    def adicionar_sinonimo_precificacao(self, chave_logica: str, sinonimo: str) -> None:
        chave = (chave_logica or "").strip()
        sinonimo = (sinonimo or "").strip()
        if not chave or not sinonimo:
            return
        atual = self.mapa_colunas_precificacao()
        lista = list(atual.get(chave, []))
        if sinonimo not in lista:
            lista.append(sinonimo)
        atual[chave] = lista
        self.definir_mapa_colunas_precificacao(atual)

    def remover_sinonimo_precificacao(self, chave_logica: str, sinonimo: str) -> None:
        atual = self.mapa_colunas_precificacao()
        if chave_logica in atual:
            atual[chave_logica] = [s for s in atual[chave_logica] if s != sinonimo]
            self.definir_mapa_colunas_precificacao(atual)

    def remover_chave_precificacao(self, chave_logica: str) -> None:
        atual = self.mapa_colunas_precificacao()
        if chave_logica in atual:
            del atual[chave_logica]
            self.definir_mapa_colunas_precificacao(atual)
        excluidos = list(self.dados.get("mapa_precificacao_excluidos", []))
        if chave_logica not in excluidos:
            excluidos.append(chave_logica)
            self.set("mapa_precificacao_excluidos", excluidos)
