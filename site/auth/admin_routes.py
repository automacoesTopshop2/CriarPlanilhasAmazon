"""
Rotas administrativas. Todas protegidas por @requer_admin.

    GET  /admin/usuarios
    POST /admin/usuarios/<id>/promover
    POST /admin/usuarios/<id>/rebaixar
    POST /admin/usuarios/<id>/desativar
    POST /admin/usuarios/<id>/ativar
    POST /admin/usuarios/<id>/reset-senha     -> retorna link de reset
    POST /admin/convites                       -> retorna link de convite
    POST /admin/convites/<id>/revogar
    GET  /admin/auditoria
"""

from __future__ import annotations

from datetime import timedelta

from flask import (
    Blueprint, abort, current_app, flash, jsonify, redirect, render_template,
    request, url_for
)
from flask_login import current_user, login_required
from flask_wtf.csrf import validate_csrf
from wtforms.validators import ValidationError as WTFValidationError

from .forms import NovoConviteForm
from .models import Convite, EventoAuth, TokenReset, Usuario, db, _utcnow
from .security import (
    gerar_token_url_safe,
    hash_token,
    normalizar_email,
    registrar_evento,
    requer_admin,
)


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# Validade dos links
HORAS_VALIDADE_CONVITE = 48
HORAS_VALIDADE_RESET = 24


def _valida_csrf_ajax():
    """Valida X-CSRFToken (ou form csrf_token) — usado em POSTs JSON."""
    if not current_app.config.get("WTF_CSRF_ENABLED", True):
        return  # bypass em testes
    token = request.headers.get("X-CSRFToken") or request.form.get("csrf_token")
    if not token:
        abort(400, description="CSRF token ausente.")
    try:
        validate_csrf(token)
    except Exception:
        abort(400, description="CSRF token inválido.")


# =============================================================================
# /admin/usuarios
# =============================================================================
@admin_bp.route("/usuarios", methods=["GET"])
@login_required
@requer_admin
def lista_usuarios():
    usuarios = db.session.query(Usuario).order_by(Usuario.criado_em.desc()).all()
    convites = (
        db.session.query(Convite)
        .filter(Convite.usado_em.is_(None))
        .order_by(Convite.criado_em.desc())
        .all()
    )
    form = NovoConviteForm()
    return render_template(
        "admin/usuarios.html",
        usuarios=usuarios,
        convites=convites,
        form=form,
        active="admin_usuarios",
    )


@admin_bp.route("/usuarios/<id>/promover", methods=["POST"])
@login_required
@requer_admin
def promover(id: str):
    _valida_csrf_ajax()
    u = db.session.get(Usuario, id)
    if not u:
        abort(404)
    u.papel = "admin"
    db.session.commit()
    registrar_evento("promocao", usuario_id=u.id, detalhes=f"por {current_user.id}")
    return jsonify({"sucesso": True})


@admin_bp.route("/usuarios/<id>/rebaixar", methods=["POST"])
@login_required
@requer_admin
def rebaixar(id: str):
    _valida_csrf_ajax()
    u = db.session.get(Usuario, id)
    if not u:
        abort(404)
    if u.id == current_user.id:
        return jsonify({"sucesso": False, "mensagem": "Você não pode rebaixar a si mesmo."}), 400
    # Garante pelo menos 1 admin restante
    admins_ativos = (
        db.session.query(Usuario)
        .filter(Usuario.papel == "admin", Usuario.ativo == True, Usuario.id != u.id)
        .count()
    )
    if admins_ativos == 0:
        return jsonify({"sucesso": False, "mensagem": "Precisa haver ao menos um administrador ativo."}), 400
    u.papel = "usuario"
    db.session.commit()
    registrar_evento("rebaixamento", usuario_id=u.id, detalhes=f"por {current_user.id}")
    return jsonify({"sucesso": True})


@admin_bp.route("/usuarios/<id>/desativar", methods=["POST"])
@login_required
@requer_admin
def desativar(id: str):
    _valida_csrf_ajax()
    u = db.session.get(Usuario, id)
    if not u:
        abort(404)
    if u.id == current_user.id:
        return jsonify({"sucesso": False, "mensagem": "Você não pode desativar a si mesmo."}), 400
    # Se o alvo é admin ativo, garante que sobra ao menos 1 admin após desativar
    if u.papel == "admin" and u.ativo:
        outros_admins_ativos = (
            db.session.query(Usuario)
            .filter(Usuario.papel == "admin", Usuario.ativo == True, Usuario.id != u.id)
            .count()
        )
        if outros_admins_ativos == 0:
            return jsonify({"sucesso": False, "mensagem": "Precisa haver ao menos um administrador ativo."}), 400
    u.ativo = False
    # Invalida sessões ativas dele (incrementa sessao_versao)
    u.sessao_versao = (u.sessao_versao or 1) + 1
    db.session.commit()
    registrar_evento("desativacao", usuario_id=u.id, detalhes=f"por {current_user.id}")
    return jsonify({"sucesso": True})


@admin_bp.route("/usuarios/<id>/ativar", methods=["POST"])
@login_required
@requer_admin
def ativar(id: str):
    _valida_csrf_ajax()
    u = db.session.get(Usuario, id)
    if not u:
        abort(404)
    u.ativo = True
    db.session.commit()
    registrar_evento("ativacao", usuario_id=u.id, detalhes=f"por {current_user.id}")
    return jsonify({"sucesso": True})


@admin_bp.route("/usuarios/<id>/codigo-externo", methods=["POST"])
@login_required
@requer_admin
def alterar_codigo_externo(id: str):
    """Define/altera o codigo_externo do usuário (usado em chamadas BDAmazon)."""
    _valida_csrf_ajax()
    u = db.session.get(Usuario, id)
    if not u:
        abort(404)
    data = request.get_json(silent=True) or {}
    novo = (data.get("codigo_externo") or "").strip() or None
    if novo and (len(novo) > 64 or any(c.isspace() for c in novo)):
        return jsonify({
            "sucesso": False,
            "mensagem": "codigo_externo deve ter até 64 caracteres sem espaços.",
        }), 400
    if novo:
        ja = (
            db.session.query(Usuario)
            .filter(Usuario.codigo_externo == novo, Usuario.id != u.id)
            .first()
        )
        if ja:
            return jsonify({
                "sucesso": False,
                "mensagem": f"codigo_externo já em uso por {ja.email}.",
            }), 400
    u.codigo_externo = novo
    db.session.commit()
    registrar_evento(
        "codigo_externo_alterado",
        usuario_id=u.id,
        detalhes=f"por {current_user.id}; novo={novo}",
    )
    return jsonify({"sucesso": True, "codigo_externo": novo})


@admin_bp.route("/usuarios/<id>/reset-senha", methods=["POST"])
@login_required
@requer_admin
def reset_senha(id: str):
    _valida_csrf_ajax()
    u = db.session.get(Usuario, id)
    if not u:
        abort(404)

    token = gerar_token_url_safe(32)
    tr = TokenReset(
        usuario_id=u.id,
        token_hash=hash_token(token),
        expira_em=_utcnow() + timedelta(hours=HORAS_VALIDADE_RESET),
    )
    db.session.add(tr)
    db.session.commit()
    registrar_evento("reset_emitido", usuario_id=u.id, detalhes=f"por {current_user.id}")

    link = url_for("auth.reset", token=token, _external=True)
    return jsonify({
        "sucesso": True,
        "link": link,
        "expira_horas": HORAS_VALIDADE_RESET,
        "email": u.email,
    })


# =============================================================================
# /admin/convites
# =============================================================================
@admin_bp.route("/convites", methods=["POST"])
@login_required
@requer_admin
def criar_convite():
    form = NovoConviteForm()
    if not form.validate_on_submit():
        msg = "; ".join(
            f"{f}: {','.join(errs)}" for f, errs in form.errors.items()
        ) or "Dados inválidos."
        return jsonify({"sucesso": False, "mensagem": msg}), 400

    email = normalizar_email(form.email.data)
    papel = form.papel.data if form.papel.data in ("admin", "usuario") else "usuario"

    # Se já existe usuário com esse e-mail, recusa
    if db.session.query(Usuario).filter_by(email=email).first():
        return jsonify({"sucesso": False, "mensagem": "Já existe um usuário com esse e-mail."}), 400

    token = gerar_token_url_safe(32)
    convite = Convite(
        email=email,
        papel=papel,
        token_hash=hash_token(token),
        criado_por=current_user.id,
        expira_em=_utcnow() + timedelta(hours=HORAS_VALIDADE_CONVITE),
    )
    db.session.add(convite)
    db.session.commit()
    registrar_evento(
        "convite_emitido",
        usuario_id=current_user.id,
        email_tentado=email,
        detalhes=f"papel={papel}",
    )

    link = url_for("auth.registro", token=token, _external=True)
    return jsonify({
        "sucesso": True,
        "link": link,
        "email": email,
        "papel": papel,
        "expira_horas": HORAS_VALIDADE_CONVITE,
    })


@admin_bp.route("/convites/<id>/revogar", methods=["POST"])
@login_required
@requer_admin
def revogar_convite(id: str):
    _valida_csrf_ajax()
    c = db.session.get(Convite, id)
    if not c:
        abort(404)
    db.session.delete(c)
    db.session.commit()
    registrar_evento("convite_revogado", usuario_id=current_user.id, detalhes=f"convite={id}")
    return jsonify({"sucesso": True})


# =============================================================================
# /admin/auditoria
# =============================================================================
@admin_bp.route("/auditoria", methods=["GET"])
@login_required
@requer_admin
def auditoria():
    # Filtros simples por querystring
    evento = request.args.get("evento") or None
    email = request.args.get("email") or None
    limite = int(request.args.get("limite", 200))
    limite = max(1, min(limite, 1000))

    q = db.session.query(EventoAuth)
    if evento:
        q = q.filter(EventoAuth.evento == evento)
    if email:
        q = q.filter(EventoAuth.email_tentado.ilike(f"%{email.lower()}%"))

    eventos = q.order_by(EventoAuth.criado_em.desc()).limit(limite).all()

    return render_template(
        "admin/auditoria.html",
        eventos=eventos,
        filtro_evento=evento,
        filtro_email=email,
        limite=limite,
        active="admin_auditoria",
    )
