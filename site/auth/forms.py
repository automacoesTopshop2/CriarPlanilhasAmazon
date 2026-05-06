"""WTForms — validação de input + CSRF automático via Flask-WTF."""

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField
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
