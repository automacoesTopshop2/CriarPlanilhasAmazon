"""
Blueprint /configuracoes — só admin.

UI: site/templates/admin/configuracoes.html (abas: Arquivos, Valores Fixos,
    Mapeamento de Colunas, Prefixos de Conta, OneDrive).

API:
    GET  /api/config
    PUT  /api/config/arquivos
    PUT  /api/config/onedrive
    POST /api/config/valores-fixos
    PUT  /api/config/valores-fixos/<nome>
    DELETE /api/config/valores-fixos/<nome>
    POST /api/config/mapa-colunas/<chave>     -> adiciona sinônimo
    DELETE /api/config/mapa-colunas/<chave>/<sinonimo>
    DELETE /api/config/mapa-colunas/<chave>   -> remove a chave inteira
    POST /api/config/mapa-precificacao/<chave>     -> adiciona sinônimo (precificação)
    DELETE /api/config/mapa-precificacao/<chave>/<sinonimo>
    DELETE /api/config/mapa-precificacao/<chave>   -> remove a chave inteira
    POST /api/config/prefixos                  -> {prefixo, conta}
    PUT  /api/config/prefixos/<prefixo>        -> {prefixo_novo, conta}
    DELETE /api/config/prefixos/<prefixo>
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, jsonify, render_template, request
from flask_login import current_user, login_required
from flask_wtf.csrf import validate_csrf

from .security import registrar_evento, requer_admin


config_bp = Blueprint("config_admin", __name__)


def _csrf():
    if not current_app.config.get("WTF_CSRF_ENABLED", True):
        return  # bypass em testes
    token = request.headers.get("X-CSRFToken") or request.form.get("csrf_token")
    if not token:
        abort(400, description="CSRF token ausente.")
    try:
        validate_csrf(token)
    except Exception:
        abort(400, description="CSRF token inválido.")


def _gerenciador():
    """Atalho para o GerenciadorConfig anexado ao app."""
    g = current_app.config.get("CONFIG_MANAGER")
    if g is None:
        from core.config_manager import GerenciadorConfig
        g = GerenciadorConfig()
        current_app.config["CONFIG_MANAGER"] = g
    return g


def _config_app():
    """Atalho para a Configuracoes ativa (mesma do web_app)."""
    return current_app.config.get("APP_CONFIG")


def _reaplica_config():
    """Reaplica gerenciador na Configuracoes em memória após uma alteração."""
    cfg = _config_app()
    if cfg is not None:
        cfg.aplicar_gerenciador(_gerenciador())


def _sharepoint_status() -> dict:
    """Estado da config SharePoint (link + flag), sem expor secrets."""
    import os as _os
    g = _gerenciador()
    return {
        "link_precificacao": g.get("sharepoint_link_precificacao") or "",
        "sync_no_startup": bool(g.get("sharepoint_sync_no_startup", True)),
        "credenciais_configuradas": all([
            (_os.getenv("SHAREPOINT_TENANT_ID") or "").strip(),
            (_os.getenv("SHAREPOINT_CLIENT_ID") or "").strip(),
            (_os.getenv("SHAREPOINT_CLIENT_SECRET") or "").strip(),
        ]),
    }


def _snapshot():
    """Estado atual completo para popular a UI."""
    g = _gerenciador()
    cfg = _config_app()

    # Combina mapa default + custom para mostrar o que está em uso agora
    mapa_colunas_efetivo = {}
    if cfg:
        mapa_colunas_efetivo = {k: list(v) for k, v in cfg.mapa_colunas_descricao.items()}
    mapa_prefixo_efetivo = {}
    if cfg:
        mapa_prefixo_efetivo = dict(cfg.mapa_prefixo_conta)
    mapa_precificacao_efetivo = {}
    if cfg:
        mapa_precificacao_efetivo = {
            k: list(v) for k, v in getattr(cfg, "mapa_colunas_precificacao", {}).items()
        }

    return {
        "arquivos": {
            "arquivo_precificacao": g.get("arquivo_precificacao"),
            "arquivo_descricao": g.get("arquivo_descricao"),
            "arquivo_remover": g.get("arquivo_remover"),
            "arquivo_substituir": g.get("arquivo_substituir"),
            "url_base_imagens": g.get("url_base_imagens"),
        },
        "onedrive": list(g.caminhos_onedrive()),
        "valores_fixos": dict(cfg.valores_fixos_padrao) if cfg else {},
        "valores_fixos_customizados": g.valores_fixos_customizados(),
        "mapa_colunas": mapa_colunas_efetivo,
        "mapa_colunas_customizados": g.mapa_colunas_descricao(),
        "mapa_precificacao": mapa_precificacao_efetivo,
        "mapa_precificacao_customizados": g.mapa_colunas_precificacao(),
        "mapa_prefixo": mapa_prefixo_efetivo,
        "mapa_prefixo_customizados": g.mapa_prefixo_conta(),
        "sharepoint": _sharepoint_status(),
    }


# =============================================================================
# Página
# =============================================================================
@config_bp.route("/configuracoes", methods=["GET"])
@login_required
@requer_admin
def pagina_configuracoes():
    return render_template(
        "admin/configuracoes.html",
        active="configuracoes",
        snapshot=_snapshot(),
    )


# =============================================================================
# API
# =============================================================================
@config_bp.route("/api/config", methods=["GET"])
@login_required
@requer_admin
def api_config():
    return jsonify(_snapshot())


# ---- arquivos ----

@config_bp.route("/api/config/arquivos", methods=["PUT"])
@login_required
@requer_admin
def api_arquivos():
    _csrf()
    data = request.get_json(silent=True) or {}
    g = _gerenciador()
    for chave in (
        "arquivo_precificacao",
        "arquivo_descricao",
        "arquivo_remover",
        "arquivo_substituir",
        "url_base_imagens",
    ):
        if chave in data:
            g.set(chave, str(data[chave]).strip())
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


# ---- onedrive ----

@config_bp.route("/api/config/onedrive", methods=["PUT"])
@login_required
@requer_admin
def api_onedrive():
    _csrf()
    data = request.get_json(silent=True) or {}
    caminhos = data.get("caminhos") or []
    g = _gerenciador()
    g.definir_caminhos_onedrive([str(c) for c in caminhos])
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


# ---- valores fixos ----

@config_bp.route("/api/config/valores-fixos", methods=["POST"])
@login_required
@requer_admin
def api_valores_fixos_add():
    _csrf()
    data = request.get_json(silent=True) or {}
    coluna = (data.get("coluna") or "").strip()
    valor = (data.get("valor") or "").strip()
    if not coluna:
        return jsonify({"sucesso": False, "mensagem": "Nome da coluna é obrigatório."}), 400
    _gerenciador().adicionar_valor_fixo(coluna, valor)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


@config_bp.route("/api/config/valores-fixos/<path:nome>", methods=["PUT"])
@login_required
@requer_admin
def api_valores_fixos_edit(nome: str):
    _csrf()
    data = request.get_json(silent=True) or {}
    novo_nome = (data.get("nome_novo") or nome).strip()
    valor = (data.get("valor") or "").strip()
    _gerenciador().atualizar_valor_fixo(nome, novo_nome, valor)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


@config_bp.route("/api/config/valores-fixos/<path:nome>", methods=["DELETE"])
@login_required
@requer_admin
def api_valores_fixos_del(nome: str):
    _csrf()
    _gerenciador().remover_valor_fixo(nome)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


# ---- mapa de colunas (sinônimos por campo lógico) ----

@config_bp.route("/api/config/mapa-colunas/<chave>", methods=["POST"])
@login_required
@requer_admin
def api_mapa_colunas_add(chave: str):
    _csrf()
    data = request.get_json(silent=True) or {}
    sinonimo = (data.get("sinonimo") or "").strip()
    if not sinonimo:
        return jsonify({"sucesso": False, "mensagem": "Sinônimo vazio."}), 400
    _gerenciador().adicionar_sinonimo_coluna(chave, sinonimo)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


@config_bp.route("/api/config/mapa-colunas/<chave>/<path:sinonimo>", methods=["DELETE"])
@login_required
@requer_admin
def api_mapa_colunas_del_sinonimo(chave: str, sinonimo: str):
    _csrf()
    g = _gerenciador()
    cfg = _config_app()
    if cfg:
        g.inicializar_mapa_colunas_de_efetivo({k: list(v) for k, v in cfg.mapa_colunas_descricao.items()})
    g.remover_sinonimo_coluna(chave, sinonimo)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


@config_bp.route("/api/config/mapa-colunas/<chave>", methods=["DELETE"])
@login_required
@requer_admin
def api_mapa_colunas_del_chave(chave: str):
    _csrf()
    g = _gerenciador()
    cfg = _config_app()
    if cfg:
        g.inicializar_mapa_colunas_de_efetivo({k: list(v) for k, v in cfg.mapa_colunas_descricao.items()})
    g.remover_chave_coluna(chave)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


# ---- mapa de colunas da PRECIFICAÇÃO (sinônimos por campo lógico) ----

@config_bp.route("/api/config/mapa-precificacao/<chave>", methods=["POST"])
@login_required
@requer_admin
def api_mapa_precificacao_add(chave: str):
    _csrf()
    data = request.get_json(silent=True) or {}
    sinonimo = (data.get("sinonimo") or "").strip()
    if not sinonimo:
        return jsonify({"sucesso": False, "mensagem": "Sinônimo vazio."}), 400
    _gerenciador().adicionar_sinonimo_precificacao(chave, sinonimo)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


@config_bp.route("/api/config/mapa-precificacao/<chave>/<path:sinonimo>", methods=["DELETE"])
@login_required
@requer_admin
def api_mapa_precificacao_del_sinonimo(chave: str, sinonimo: str):
    _csrf()
    g = _gerenciador()
    cfg = _config_app()
    if cfg:
        g.inicializar_mapa_precificacao_de_efetivo({k: list(v) for k, v in cfg.mapa_colunas_precificacao.items()})
    g.remover_sinonimo_precificacao(chave, sinonimo)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


@config_bp.route("/api/config/mapa-precificacao/<chave>", methods=["DELETE"])
@login_required
@requer_admin
def api_mapa_precificacao_del_chave(chave: str):
    _csrf()
    g = _gerenciador()
    cfg = _config_app()
    if cfg:
        g.inicializar_mapa_precificacao_de_efetivo({k: list(v) for k, v in cfg.mapa_colunas_precificacao.items()})
    g.remover_chave_precificacao(chave)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


# ---- prefixos de conta ----

@config_bp.route("/api/config/prefixos", methods=["POST"])
@login_required
@requer_admin
def api_prefixo_add():
    _csrf()
    data = request.get_json(silent=True) or {}
    prefixo = (data.get("prefixo") or "").strip().upper()
    conta = (data.get("conta") or "").strip()
    if not prefixo or not conta:
        return jsonify({"sucesso": False, "mensagem": "Prefixo e conta são obrigatórios."}), 400
    _gerenciador().adicionar_prefixo(prefixo, conta)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


@config_bp.route("/api/config/prefixos/<path:prefixo>", methods=["PUT"])
@login_required
@requer_admin
def api_prefixo_edit(prefixo: str):
    _csrf()
    data = request.get_json(silent=True) or {}
    prefixo_novo = (data.get("prefixo_novo") or prefixo).strip().upper()
    conta = (data.get("conta") or "").strip()
    if not prefixo_novo or not conta:
        return jsonify({"sucesso": False, "mensagem": "Prefixo e conta são obrigatórios."}), 400
    g = _gerenciador()
    cfg = _config_app()
    if cfg:
        g.inicializar_mapa_prefixo_de_efetivo(dict(cfg.mapa_prefixo_conta))
    g.atualizar_prefixo(prefixo, prefixo_novo, conta)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


@config_bp.route("/api/config/prefixos/<path:prefixo>", methods=["DELETE"])
@login_required
@requer_admin
def api_prefixo_del(prefixo: str):
    _csrf()
    g = _gerenciador()
    cfg = _config_app()
    if cfg:
        g.inicializar_mapa_prefixo_de_efetivo(dict(cfg.mapa_prefixo_conta))
    g.remover_prefixo(prefixo)
    _reaplica_config()
    return jsonify({"sucesso": True, "estado": _snapshot()})


# =============================================================================
# SharePoint
# =============================================================================
def _sharepoint_client_ou_erro():
    """Retorna (cliente, None) ou (None, mensagem-de-erro)."""
    try:
        from core.sharepoint_client import SharePointClient
    except ImportError as e:
        return None, f"msal não instalado: {e}"
    cliente = SharePointClient.do_ambiente()
    if cliente is None:
        return None, (
            "Credenciais ausentes. Defina SHAREPOINT_TENANT_ID, "
            "SHAREPOINT_CLIENT_ID e SHAREPOINT_CLIENT_SECRET no .env."
        )
    return cliente, None


@config_bp.route("/api/config/sharepoint", methods=["PUT"])
@login_required
@requer_admin
def api_sharepoint_config():
    """Salva o link de compartilhamento e a flag de sync no startup."""
    _csrf()
    data = request.get_json(silent=True) or {}
    g = _gerenciador()
    if "link_precificacao" in data:
        g.set("sharepoint_link_precificacao", str(data["link_precificacao"]).strip())
    if "sync_no_startup" in data:
        g.set("sharepoint_sync_no_startup", bool(data["sync_no_startup"]))
    return jsonify({"sucesso": True, "estado": _snapshot()})


@config_bp.route("/api/config/sharepoint/testar", methods=["POST"])
@login_required
@requer_admin
def api_sharepoint_testar():
    """Valida o link sem baixar (faz GET no DriveItem para checar acesso)."""
    _csrf()
    g = _gerenciador()
    link = (g.get("sharepoint_link_precificacao") or "").strip()
    if not link:
        return jsonify({"sucesso": False, "mensagem": "Cole o link da planilha primeiro."}), 400

    cliente, erro = _sharepoint_client_ou_erro()
    if erro:
        return jsonify({"sucesso": False, "mensagem": erro}), 400

    try:
        info = cliente.testar_url(link)
        return jsonify({"sucesso": True, **info})
    except Exception as e:
        return jsonify({"sucesso": False, "mensagem": str(e)}), 400


@config_bp.route("/api/config/sharepoint/sincronizar", methods=["POST"])
@login_required
def api_sharepoint_sincronizar():
    """Baixa a Precificação via share-link e grava no path local.

    Aberto a qualquer usuário autenticado: o link é configurado pelo
    admin, então o sync apenas atualiza o arquivo local — não há
    superfície de ataque (usuário não escolhe a URL)."""
    _csrf()
    g = _gerenciador()
    cfg = _config_app()
    link = (g.get("sharepoint_link_precificacao") or "").strip()
    if not link:
        return jsonify({
            "sucesso": False,
            "mensagem": "Cole o link da planilha primeiro.",
        }), 400

    cliente, erro = _sharepoint_client_ou_erro()
    if erro:
        return jsonify({"sucesso": False, "mensagem": erro}), 400

    from core.sharepoint_client import sincronizar_por_url
    destino = cfg.arquivo_precificacao if cfg else g.get("arquivo_precificacao")
    ok, msg = sincronizar_por_url(cliente, link, destino)
    if ok:
        registrar_evento(
            "sharepoint_sync_ok",
            usuario_id=current_user.id,
            detalhes=msg[:255],
        )
        return jsonify({"sucesso": True, "mensagem": msg})
    else:
        registrar_evento(
            "sharepoint_sync_falhou",
            usuario_id=current_user.id,
            detalhes=msg[:255],
        )
        return jsonify({"sucesso": False, "mensagem": msg}), 400
