"""
Rotas públicas de autenticação:
    POST /login
    POST /logout
    GET/POST /registro/<token>
    GET/POST /perfil  (autenticada)
    GET/POST /reset/<token>

Anti-enumeração, rate-limit e auditoria embutidos.
"""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlparse

from flask import (
    Blueprint, current_app, flash, redirect, render_template, request, url_for
)
from flask_login import current_user, login_required, login_user, logout_user

from .forms import LoginForm, PerfilForm, RegistroForm, TrocarSenhaForm
from .models import Convite, TokenReset, Usuario, db, _utcnow
from .security import (
    hash_senha,
    hash_token,
    normalizar_email,
    registrar_evento,
    verificar_senha,
)


auth_bp = Blueprint("auth", __name__)


# Configurações de bloqueio de conta
MAX_FALHAS = 5
DURACAO_BLOQUEIO_MIN = 15


def _eh_url_segura(target: str) -> bool:
    """next= só pode ir para URL relativa do mesmo host (anti open-redirect)."""
    if not target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(target)
    return (test.scheme in ("", "http", "https")) and (
        not test.netloc or test.netloc == ref.netloc
    )


# =============================================================================
# /login
# =============================================================================
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    form = LoginForm()
    erro: str | None = None

    if form.validate_on_submit():
        # Aplicar rate-limit declarado em web_app.py
        email = normalizar_email(form.email.data)
        senha = form.senha.data or ""

        usuario = db.session.query(Usuario).filter_by(email=email).first()

        # Tempo de resposta uniforme — sempre executa argon2 (anti-enumeração)
        senha_ok = verificar_senha(usuario.senha_hash if usuario else None, senha)

        # Bloqueio
        if usuario and usuario.esta_bloqueado:
            registrar_evento(
                "login_bloqueado",
                usuario_id=usuario.id,
                email_tentado=email,
                detalhes="Tentativa durante bloqueio",
            )
            erro = "Conta temporariamente bloqueada por excesso de tentativas. Aguarde alguns minutos."
        elif not usuario or not usuario.ativo:
            registrar_evento("login_falha", email_tentado=email, detalhes="usuário inexistente ou desativado")
            erro = "E-mail ou senha incorretos."
        elif not senha_ok:
            usuario.falhas_consecutivas = (usuario.falhas_consecutivas or 0) + 1
            if usuario.falhas_consecutivas >= MAX_FALHAS:
                usuario.bloqueado_ate = _utcnow() + timedelta(minutes=DURACAO_BLOQUEIO_MIN)
                registrar_evento(
                    "bloqueio",
                    usuario_id=usuario.id,
                    email_tentado=email,
                    detalhes=f"Bloqueado após {MAX_FALHAS} falhas consecutivas",
                )
            db.session.commit()
            registrar_evento("login_falha", usuario_id=usuario.id, email_tentado=email)
            erro = "E-mail ou senha incorretos."
        else:
            # Sucesso
            usuario.falhas_consecutivas = 0
            usuario.bloqueado_ate = None
            usuario.ultimo_login = _utcnow()
            db.session.commit()
            login_user(usuario, remember=bool(form.lembrar.data))
            registrar_evento("login_ok", usuario_id=usuario.id, email_tentado=email)

            destino = request.args.get("next") or request.form.get("next")
            if destino and _eh_url_segura(destino):
                return redirect(destino)
            return redirect(url_for("home"))

    return render_template("auth/login.html", form=form, erro=erro, active="login")


# =============================================================================
# /logout
# =============================================================================
@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    uid = current_user.id
    logout_user()
    registrar_evento("logout", usuario_id=uid)
    return redirect(url_for("auth.login"))


# =============================================================================
# /registro/<token>
# =============================================================================
@auth_bp.route("/registro/<token>", methods=["GET", "POST"])
def registro(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    convite = (
        db.session.query(Convite)
        .filter_by(token_hash=hash_token(token))
        .first()
    )

    if not convite or not convite.esta_valido:
        return render_template("auth/registro_invalido.html"), 400

    form = RegistroForm()
    erro: str | None = None

    if form.validate_on_submit():
        # Cria usuário com e-mail vindo do convite (não do form — imutável)
        ja_existe = db.session.query(Usuario).filter_by(email=convite.email).first()
        if ja_existe:
            erro = "Já existe uma conta com esse e-mail. Faça login ou peça um reset de senha ao admin."
        else:
            usuario = Usuario(
                email=convite.email,
                nome=form.nome.data.strip(),
                senha_hash=hash_senha(form.senha.data),
                papel=convite.papel,
                ativo=True,
            )
            convite.usado_em = _utcnow()
            db.session.add(usuario)
            db.session.commit()
            registrar_evento(
                "convite_usado",
                usuario_id=usuario.id,
                email_tentado=convite.email,
                detalhes=f"papel={convite.papel}",
            )
            login_user(usuario)
            return redirect(url_for("home"))

    return render_template(
        "auth/registro.html",
        form=form,
        email=convite.email,
        papel=convite.papel,
        token=token,
        erro=erro,
    )


# =============================================================================
# /perfil
# =============================================================================
@auth_bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    form = PerfilForm(nome=current_user.nome)
    msg_ok: str | None = None
    erro: str | None = None

    if form.validate_on_submit():
        # Atualizar nome
        novo_nome = (form.nome.data or "").strip()
        mudou_nome = novo_nome and novo_nome != current_user.nome

        # Trocar senha (opcional, só se nova_senha preenchida)
        mudar_senha = bool(form.nova_senha.data)

        if mudar_senha:
            if not verificar_senha(current_user.senha_hash, form.senha_atual.data or ""):
                erro = "Senha atual incorreta."
            else:
                current_user.senha_hash = hash_senha(form.nova_senha.data)
                # invalida sessões antigas
                current_user.sessao_versao = (current_user.sessao_versao or 1) + 1
                registrar_evento("troca_senha", usuario_id=current_user.id)

        if not erro:
            if mudou_nome:
                current_user.nome = novo_nome
            db.session.commit()
            msg_ok = "Perfil atualizado."
            if mudar_senha:
                # força re-login porque sessao_versao mudou
                logout_user()
                return redirect(url_for("auth.login"))

    return render_template("auth/perfil.html", form=form, msg_ok=msg_ok, erro=erro)


# =============================================================================
# /reset/<token>  — reset de senha emitido pelo admin
# =============================================================================
@auth_bp.route("/reset/<token>", methods=["GET", "POST"])
def reset(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    tr = (
        db.session.query(TokenReset)
        .filter_by(token_hash=hash_token(token))
        .first()
    )
    if not tr or not tr.esta_valido:
        return render_template("auth/registro_invalido.html"), 400

    form = TrocarSenhaForm()
    # Em reset não temos senha antiga — sobrescrevemos validação
    form.senha_atual.validators = []
    form.senha_atual.data = "ignorado"  # não exibido

    erro: str | None = None
    if request.method == "POST":
        if form.nova_senha.data and form.confirmacao.data:
            if form.nova_senha.data != form.confirmacao.data:
                erro = "As senhas não conferem."
            else:
                from .security import validar_forca_senha
                erro = validar_forca_senha(form.nova_senha.data)
        else:
            erro = "Preencha a nova senha."

        if not erro:
            usuario = db.session.get(Usuario, tr.usuario_id)
            usuario.senha_hash = hash_senha(form.nova_senha.data)
            usuario.sessao_versao = (usuario.sessao_versao or 1) + 1
            usuario.falhas_consecutivas = 0
            usuario.bloqueado_ate = None
            tr.usado_em = _utcnow()
            db.session.commit()
            registrar_evento("reset_senha", usuario_id=usuario.id)
            return render_template("auth/reset_ok.html", email=usuario.email)

    return render_template("auth/reset.html", form=form, erro=erro, token=token)
