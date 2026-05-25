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

from .forms import (
    CodigoOtpForm,
    ConfirmarEnrollment2FAForm,
    Desabilitar2FAForm,
    LoginForm,
    PerfilForm,
    RegenerarBackupCodesForm,
    RegistroForm,
    TrocarSenhaForm,
)
from .models import Convite, TokenReset, Usuario, db, _utcnow
from .security import (
    hash_senha,
    hash_token,
    normalizar_email,
    registrar_evento,
    verificar_senha,
)
from . import totp_challenge, totp_service


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
            # Credenciais OK — agora decide entre: 2FA ativo, enrollment, ou login direto (bypass)
            usuario.falhas_consecutivas = 0
            usuario.bloqueado_ate = None
            db.session.commit()

            destino = request.args.get("next") or request.form.get("next")
            destino_seguro = destino if destino and _eh_url_segura(destino) else None

            if usuario.totp_enabled:
                # Já tem 2FA — emite desafio e manda para a tela de código.
                temp_token, _desafio = totp_challenge.criar_desafio(
                    usuario,
                    totp_challenge.PROPOSITO_VERIFICACAO,
                    lembrar=bool(form.lembrar.data),
                )
                registrar_evento(
                    "2fa_desafio_emitido",
                    usuario_id=usuario.id,
                    email_tentado=email,
                    detalhes="verificacao",
                )
                return render_template(
                    "auth/2fa_verificar.html",
                    form=CodigoOtpForm(temp_token=temp_token),
                    proximo=destino_seguro,
                    ttl=totp_challenge._ttl_segundos(),
                )

            if usuario.precisa_configurar_2fa:
                # Senha OK mas precisa configurar 2FA antes de logar.
                temp_token, _desafio = totp_challenge.criar_desafio(
                    usuario,
                    totp_challenge.PROPOSITO_ENROLLMENT,
                    lembrar=bool(form.lembrar.data),
                )
                registrar_evento(
                    "2fa_desafio_emitido",
                    usuario_id=usuario.id,
                    email_tentado=email,
                    detalhes="enrollment",
                )
                return redirect(url_for("auth.dois_fatores_configurar", t=temp_token,
                                        next=destino_seguro or ""))

            # Bypass: sem 2FA — login direto.
            usuario.ultimo_login = _utcnow()
            db.session.commit()
            login_user(usuario, remember=bool(form.lembrar.data))
            registrar_evento(
                "login_ok",
                usuario_id=usuario.id,
                email_tentado=email,
                detalhes="sem_2fa (bypass)",
            )
            if destino_seguro:
                return redirect(destino_seguro)
            return redirect(url_for("home"))

    return render_template("auth/login.html", form=form, erro=erro, active="login")


# =============================================================================
# /login/verificar-2fa  (passo 2 do login quando totp_enabled)
# =============================================================================
@auth_bp.route("/login/verificar-2fa", methods=["POST"])
def login_verificar_2fa():
    form = CodigoOtpForm()
    proximo = request.args.get("next") or request.form.get("next")
    proximo_seguro = proximo if proximo and _eh_url_segura(proximo) else None

    if not form.validate_on_submit():
        # CSRF/temp_token ausente: manda de volta pro /login (UX simples).
        return redirect(url_for("auth.login"))

    try:
        desafio, usuario = totp_challenge.carregar_desafio(
            form.temp_token.data,
            totp_challenge.PROPOSITO_VERIFICACAO,
        )
    except totp_challenge.DesafioInvalido as e:
        registrar_evento(
            "2fa_falha",
            email_tentado=None,
            detalhes=f"desafio inválido: {e}",
        )
        return render_template(
            "auth/2fa_verificar.html",
            form=form,
            proximo=proximo_seguro,
            ttl=totp_challenge._ttl_segundos(),
            erro="Sessão de 2FA expirou ou é inválida. Faça login novamente.",
            fatal=True,
        )

    if not totp_service.verificar_codigo(usuario, form.codigo.data or ""):
        totp_challenge.registrar_falha(desafio)
        registrar_evento(
            "2fa_falha",
            usuario_id=usuario.id,
            detalhes=f"código inválido (tentativa {desafio.tentativas_falhas})",
        )
        restantes = max(0, totp_challenge.MAX_TENTATIVAS - desafio.tentativas_falhas)
        return render_template(
            "auth/2fa_verificar.html",
            form=form,
            proximo=proximo_seguro,
            ttl=totp_challenge._ttl_segundos(),
            erro=(
                "Código inválido."
                if restantes > 0
                else "Muitas tentativas erradas. Faça login novamente."
            ),
            fatal=restantes == 0,
        )

    # Sucesso — consome desafio, loga, redireciona
    totp_challenge.consumir_desafio(desafio)
    usuario.ultimo_login = _utcnow()
    db.session.commit()
    login_user(usuario, remember=bool(desafio.lembrar))
    registrar_evento("2fa_ok", usuario_id=usuario.id, detalhes="login após 2FA")
    if proximo_seguro:
        return redirect(proximo_seguro)
    return redirect(url_for("home"))


# =============================================================================
# /2fa/configurar  — enrollment (forçado no /login OU iniciado em /perfil)
# =============================================================================
def _abrir_enrollment_via_temp_token(temp_token: str):
    """Retorna (desafio, usuario) se enrollment válido — senão None."""
    try:
        return totp_challenge.carregar_desafio(
            temp_token, totp_challenge.PROPOSITO_ENROLLMENT
        )
    except totp_challenge.DesafioInvalido:
        return None, None


@auth_bp.route("/2fa/configurar", methods=["GET", "POST"])
def dois_fatores_configurar():
    """
    Enrollment 2FA. Dois caminhos de entrada:
      1) Após /login sem 2FA: ?t=<temp_token> (usuário não logado ainda).
      2) Via /perfil de usuário já logado: sem t (current_user é fonte).
    """
    proximo = request.args.get("next") or request.form.get("next") or ""
    proximo_seguro = proximo if proximo and _eh_url_segura(proximo) else None

    temp_token = request.args.get("t") or request.form.get("t") or ""
    desafio = None
    usuario = None

    if temp_token:
        desafio, usuario = _abrir_enrollment_via_temp_token(temp_token)
        if not usuario:
            return render_template(
                "auth/2fa_enroll.html",
                erro="Sessão de configuração expirada. Faça login novamente.",
                fatal=True,
            )
    elif current_user.is_authenticated:
        usuario = current_user
    else:
        return redirect(url_for("auth.login"))

    # Gera (ou regenera, se expirado) o secret pendente.
    # SQLite devolve datetime naive — normaliza para UTC antes de comparar.
    def _pending_expirou() -> bool:
        if not usuario.totp_pending_expires_at:
            return True
        from datetime import timezone as _tz
        exp = usuario.totp_pending_expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=_tz.utc)
        return exp <= _utcnow()

    if not usuario.totp_secret_pending_encrypted or _pending_expirou():
        totp_service.gerar_secret_pendente(usuario)

    # Para mostrar URI/QR/secret novamente precisamos decriptar o pending
    from .totp_crypto import decrypt_totp_secret, TOTPCryptoError
    try:
        secret = decrypt_totp_secret(usuario.totp_secret_pending_encrypted)
    except TOTPCryptoError:
        # Chave rotacionada no meio de um enrollment — regenera.
        totp_service.gerar_secret_pendente(usuario)
        secret = decrypt_totp_secret(usuario.totp_secret_pending_encrypted)
    import pyotp
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=usuario.email, issuer_name=totp_service._issuer()
    )
    qr_b64 = totp_service._gerar_qr_base64(uri)

    form = ConfirmarEnrollment2FAForm()
    erro = None
    if request.method == "POST" and form.validate_on_submit():
        if not totp_service.confirmar_2fa(usuario, form.codigo.data or ""):
            erro = "Código inválido. Confira o relógio do seu celular e tente de novo."
        else:
            # 2FA habilitado — gera backup codes
            codigos = totp_service.regenerar_backup_codes(usuario)
            registrar_evento("2fa_habilitado", usuario_id=usuario.id)

            if temp_token and desafio:
                # Fluxo "post-login": consome desafio + faz login_user agora
                totp_challenge.consumir_desafio(desafio)
                usuario.ultimo_login = _utcnow()
                db.session.commit()
                login_user(usuario, remember=bool(desafio.lembrar))
                registrar_evento(
                    "login_ok",
                    usuario_id=usuario.id,
                    detalhes="login após enrollment 2FA",
                )

            # Mostra os backup codes uma única vez. Após o usuário clicar
            # "Concluir", redireciona para destino ou home/perfil.
            destino_final = proximo_seguro or url_for("home")
            return render_template(
                "auth/2fa_backup_codes.html",
                codigos=codigos,
                proximo=destino_final,
                contexto_enrollment=True,
            )

    return render_template(
        "auth/2fa_enroll.html",
        form=form,
        secret=secret,
        qr_b64=qr_b64,
        temp_token=temp_token or None,
        proximo=proximo_seguro,
        erro=erro,
    )


# =============================================================================
# /perfil/seguranca  — gestão do 2FA pelo próprio usuário (logado)
# =============================================================================
@auth_bp.route("/perfil/seguranca", methods=["GET"])
@login_required
def perfil_seguranca():
    restantes = (
        totp_service.codigos_backup_restantes(current_user)
        if current_user.totp_enabled
        else 0
    )
    return render_template(
        "auth/2fa_seguranca.html",
        backup_restantes=restantes,
        disable_form=Desabilitar2FAForm(),
        regen_form=RegenerarBackupCodesForm(),
    )


@auth_bp.route("/2fa/desabilitar", methods=["POST"])
@login_required
def dois_fatores_desabilitar():
    form = Desabilitar2FAForm()
    if not form.validate_on_submit():
        flash("Formulário inválido.", "erro")
        return redirect(url_for("auth.perfil_seguranca"))

    if current_user.totp_required:
        flash("2FA é obrigatório para este usuário — não pode ser desativado.", "erro")
        registrar_evento(
            "2fa_desabilitar_negado",
            usuario_id=current_user.id,
            detalhes="totp_required=true",
        )
        return redirect(url_for("auth.perfil_seguranca"))

    if not verificar_senha(current_user.senha_hash, form.senha.data or ""):
        flash("Senha incorreta.", "erro")
        registrar_evento(
            "2fa_desabilitar_falha", usuario_id=current_user.id, detalhes="senha errada"
        )
        return redirect(url_for("auth.perfil_seguranca"))

    if not totp_service.verificar_codigo(current_user, form.codigo.data or ""):
        flash("Código 2FA inválido.", "erro")
        registrar_evento(
            "2fa_desabilitar_falha", usuario_id=current_user.id, detalhes="código errado"
        )
        return redirect(url_for("auth.perfil_seguranca"))

    totp_service.desabilitar_2fa(current_user)
    registrar_evento("2fa_desabilitado", usuario_id=current_user.id)
    flash("2FA desativado.", "ok")
    return redirect(url_for("auth.perfil_seguranca"))


@auth_bp.route("/2fa/backup-codes/regenerar", methods=["POST"])
@login_required
def dois_fatores_regenerar_backup():
    form = RegenerarBackupCodesForm()
    if not form.validate_on_submit():
        flash("Formulário inválido.", "erro")
        return redirect(url_for("auth.perfil_seguranca"))

    if not current_user.totp_enabled:
        flash("Configure 2FA primeiro.", "erro")
        return redirect(url_for("auth.perfil_seguranca"))

    if not totp_service.verificar_codigo(current_user, form.codigo.data or ""):
        flash("Código 2FA inválido.", "erro")
        registrar_evento(
            "2fa_regen_falha", usuario_id=current_user.id, detalhes="código errado"
        )
        return redirect(url_for("auth.perfil_seguranca"))

    codigos = totp_service.regenerar_backup_codes(current_user)
    registrar_evento("2fa_backup_regenerado", usuario_id=current_user.id)
    return render_template(
        "auth/2fa_backup_codes.html",
        codigos=codigos,
        proximo=url_for("auth.perfil_seguranca"),
        contexto_enrollment=False,
    )


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
