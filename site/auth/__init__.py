"""
Módulo de autenticação e autorização.

Componentes:
    - models.py        : SQLAlchemy (Usuario, Convite, EventoAuth, TokenReset)
    - security.py      : hashing argon2, decorators, validações
    - forms.py         : WTForms (login, registro, perfil)
    - routes.py        : blueprint público (/login, /logout, /registro, /perfil)
    - admin_routes.py  : blueprint /admin/* (gestão de usuários, convites, auditoria)
    - bootstrap_master : criação CLI do usuário admin inicial
"""

from .models import db, Usuario, Convite, EventoAuth, TokenReset
from .security import (
    hash_senha,
    verificar_senha,
    gerar_token_url_safe,
    hash_token,
    validar_forca_senha,
    requer_admin,
    registrar_evento,
)
from .routes import auth_bp
from .admin_routes import admin_bp
from .config_routes import config_bp
from .forms import LoginForm, RegistroForm, PerfilForm, NovoConviteForm

__all__ = [
    "db",
    "Usuario",
    "Convite",
    "EventoAuth",
    "TokenReset",
    "hash_senha",
    "verificar_senha",
    "gerar_token_url_safe",
    "hash_token",
    "validar_forca_senha",
    "requer_admin",
    "registrar_evento",
    "auth_bp",
    "admin_bp",
    "config_bp",
    "LoginForm",
    "RegistroForm",
    "PerfilForm",
    "NovoConviteForm",
]
