"""WTForms — validação de input + CSRF automático via Flask-WTF."""

from flask_wtf import FlaskForm
from wtforms import BooleanField, HiddenField, PasswordField, SelectField, StringField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from .security import validar_forca_senha


class LoginForm(FlaskForm):
    email = StringField(
        "E-mail",
        validators=[DataRequired(message="Informe seu e-mail."), Email(message="E-mail inválido."), Length(max=255)],
    )
    senha = PasswordField(
        "Senha",
        validators=[DataRequired(message="Informe sua senha."), Length(max=200)],
    )
    lembrar = BooleanField("Manter-me conectado")


def _validar_senha_forte(form, field):
    erro = validar_forca_senha(field.data or "")
    if erro:
        raise ValidationError(erro)


class RegistroForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(min=2, max=200)])
    senha = PasswordField(
        "Nova senha",
        validators=[DataRequired(), Length(max=200), _validar_senha_forte],
    )
    confirmacao = PasswordField(
        "Confirmar senha",
        validators=[DataRequired(), EqualTo("senha", message="As senhas não conferem.")],
    )


class PerfilForm(FlaskForm):
    nome = StringField("Nome", validators=[DataRequired(), Length(min=2, max=200)])
    senha_atual = PasswordField("Senha atual", validators=[Length(max=200)])
    nova_senha = PasswordField("Nova senha (opcional)", validators=[Length(max=200)])
    confirmacao = PasswordField(
        "Confirmar nova senha",
        validators=[Length(max=200), EqualTo("nova_senha", message="As senhas não conferem.")],
    )

    def validate_nova_senha(self, field):
        if field.data:
            erro = validar_forca_senha(field.data)
            if erro:
                raise ValidationError(erro)


class NovoConviteForm(FlaskForm):
    email = StringField("E-mail", validators=[DataRequired(), Email(), Length(max=255)])
    papel = SelectField(
        "Papel",
        choices=[("usuario", "Usuário"), ("admin", "Administrador")],
        default="usuario",
        validators=[DataRequired()],
    )


class TrocarSenhaForm(FlaskForm):
    """Usado em /perfil quando trocando a senha por iniciativa do usuário."""
    senha_atual = PasswordField("Senha atual", validators=[DataRequired(), Length(max=200)])
    nova_senha = PasswordField(
        "Nova senha",
        validators=[DataRequired(), Length(max=200), _validar_senha_forte],
    )
    confirmacao = PasswordField(
        "Confirmar",
        validators=[DataRequired(), EqualTo("nova_senha", message="As senhas não conferem.")],
    )


# =============================================================================
# 2FA
# =============================================================================
class CodigoOtpForm(FlaskForm):
    """Formulário do passo 2: digitar código TOTP (ou backup code)."""
    temp_token = HiddenField(validators=[DataRequired()])
    codigo = StringField(
        "Código",
        validators=[
            DataRequired(message="Informe o código."),
            Length(min=6, max=32, message="Código inválido."),
        ],
    )


class ConfirmarEnrollment2FAForm(FlaskForm):
    """Passo de enrollment — confirma que o usuário escaneou o QR."""
    codigo = StringField(
        "Código do app",
        validators=[
            DataRequired(message="Informe o código gerado pelo app."),
            Length(min=6, max=10),
        ],
    )


class Desabilitar2FAForm(FlaskForm):
    """Step-up: senha + código TOTP/backup para desativar."""
    senha = PasswordField(
        "Senha atual",
        validators=[DataRequired(message="Informe sua senha."), Length(max=200)],
    )
    codigo = StringField(
        "Código 2FA",
        validators=[DataRequired(message="Informe o código atual."), Length(min=6, max=32)],
    )


class RegenerarBackupCodesForm(FlaskForm):
    """Step-up só com código (regenerar não é tão crítico quanto desativar)."""
    codigo = StringField(
        "Código 2FA",
        validators=[DataRequired(message="Informe o código atual."), Length(min=6, max=32)],
    )
