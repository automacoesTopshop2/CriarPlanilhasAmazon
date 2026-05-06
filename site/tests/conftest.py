"""
Fixtures pytest para Topshop Amazon System.

Estratégia:
    - DB efêmero: SQLite in-memory por teste
    - Talisman desligado em testes (não interfere)
    - Limiter desligado em testes (atrapalha bloqueio_account_test)
    - Bootstrapa um admin e um usuário comum em cada teste
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta

import pytest

# Garante sys.path correto antes de importar a app
_AQUI = os.path.dirname(os.path.abspath(__file__))
_SITE = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_SITE)
for p in (_RAIZ, _SITE):
    if p not in sys.path:
        sys.path.insert(0, p)
os.chdir(_RAIZ)

# Configura DB de teste antes de importar a app
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret-key-32bytes-fixed-aaa"
os.environ["ENV"] = "development"
os.environ["SESSION_COOKIE_SECURE"] = "0"

from auth import db, Usuario  # noqa: E402
from auth.security import hash_senha  # noqa: E402
import web_app  # noqa: E402


# pytest-flask instala uma autouse fixture `_push_request_context` que empurra
# `test_request_context()` durante todo o teste. O app_context implícito é
# reutilizado pelas requests do test_client, fazendo `g._login_user` persistir
# entre requests e bypassar o user_loader. Sobrescrevemos com um no-op.
@pytest.fixture(autouse=True)
def _push_request_context():
    yield


@pytest.fixture
def app():
    """Cria app com DB in-memory e Limiter desligado para testes.

    Não mantém app_context push durante o teste — cada `with app.app_context()`
    de teste/fixture cria/encerra seu próprio escopo. Caso contrário, Flask
    reutiliza o app_context externo nas requests, e g._login_user (cacheado
    durante login_user()) persiste e bypassa o user_loader em requests
    subsequentes — quebrando testes que dependem de sessao_versao.
    """
    overrides = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,  # Maioria dos testes não testa CSRF — testes específicos religam
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "RATELIMIT_ENABLED": False,
    }
    application = web_app.create_app(config_overrides=overrides)
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin(app):
    """Cria um admin para os testes."""
    with app.app_context():
        u = Usuario(
            email="admin@topshop.com.br",
            nome="Admin Master",
            senha_hash=hash_senha("SenhaForte123!"),
            papel="admin",
            ativo=True,
        )
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def usuario(app):
    """Cria um usuário comum."""
    with app.app_context():
        u = Usuario(
            email="user@topshop.com.br",
            nome="Usuario Comum",
            senha_hash=hash_senha("SenhaForte456@"),
            papel="usuario",
            ativo=True,
        )
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def login_admin(client, app, admin):
    """Faz login como admin via POST real (mais robusto que setar sessão na mão)."""
    r = client.post(
        "/login",
        data={"email": "admin@topshop.com.br", "senha": "SenhaForte123!"},
        follow_redirects=False,
    )
    assert r.status_code == 302, f"Login admin falhou: {r.status_code}"
    return admin


@pytest.fixture
def login_usuario(client, app, usuario):
    """Faz login como usuário comum via POST real."""
    r = client.post(
        "/login",
        data={"email": "user@topshop.com.br", "senha": "SenhaForte456@"},
        follow_redirects=False,
    )
    assert r.status_code == 302, f"Login usuario falhou: {r.status_code}"
    return usuario


@pytest.fixture
def app_with_csrf():
    """App com CSRF habilitado, para testes específicos de CSRF."""
    overrides = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "RATELIMIT_ENABLED": False,
    }
    application = web_app.create_app(config_overrides=overrides)
    with application.app_context():
        db.create_all()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client_with_csrf(app_with_csrf):
    return app_with_csrf.test_client()


@pytest.fixture
def app_with_ratelimit():
    """App com rate limit ativo, para testes específicos."""
    overrides = {
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "RATELIMIT_ENABLED": True,
        "RATELIMIT_HEADERS_ENABLED": True,
    }
    application = web_app.create_app(config_overrides=overrides)
    with application.app_context():
        db.create_all()
        # cria usuário válido para tentativas
        u = Usuario(
            email="alvo@topshop.com.br",
            nome="Alvo",
            senha_hash=hash_senha("SenhaForte123!"),
            papel="usuario",
            ativo=True,
        )
        db.session.add(u)
        db.session.commit()
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client_with_ratelimit(app_with_ratelimit):
    return app_with_ratelimit.test_client()
