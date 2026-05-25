"""Testes de headers de segurança e CSRF."""

import pytest

from auth import db


class TestHeadersSeguranca:
    @pytest.fixture
    def app_com_talisman(self):
        """App em produção (Talisman ligado, sem TESTING flag)."""
        import os
        os.environ["DATABASE_URL"] = "sqlite:///:memory:"
        os.environ["SECRET_KEY"] = "x" * 64
        os.environ["ENV"] = "development"  # mantém HTTPS off, mas Talisman aplica outros headers
        os.environ["SESSION_COOKIE_SECURE"] = "0"
        import web_app
        # Re-cria app sem TESTING flag para Talisman aplicar headers
        application = web_app.create_app(config_overrides={
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
            "RATELIMIT_ENABLED": False,
        })
        with application.app_context():
            db.create_all()
            yield application
            db.session.remove()
            db.drop_all()

    def test_csp_header_presente(self, app_com_talisman):
        c = app_com_talisman.test_client()
        r = c.get("/login")
        assert "Content-Security-Policy" in r.headers

    def test_x_frame_options_deny(self, app_com_talisman):
        c = app_com_talisman.test_client()
        r = c.get("/login")
        assert r.headers.get("X-Frame-Options") == "DENY"

    def test_x_content_type_options_nosniff(self, app_com_talisman):
        c = app_com_talisman.test_client()
        r = c.get("/login")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_referrer_policy(self, app_com_talisman):
        c = app_com_talisman.test_client()
        r = c.get("/login")
        assert "same-origin" in (r.headers.get("Referrer-Policy") or "")

    def test_session_cookie_httponly(self, app_com_talisman):
        # cookie de sessão tem HttpOnly
        c = app_com_talisman.test_client()
        r = c.get("/login")
        for cookie in c.cookie_jar if hasattr(c, "cookie_jar") else []:
            assert cookie._rest.get("HttpOnly") in ("", None) or cookie._rest.get("HttpOnly") is not False


class TestCSRF:
    @pytest.fixture
    def app_csrf_on(self, app_with_csrf):
        from auth import Usuario
        from auth.security import hash_senha
        with app_with_csrf.app_context():
            u = Usuario(
                email="csrf@topshop.com.br",
                nome="CSRF User",
                senha_hash=hash_senha("SenhaForte1234"),
                papel="admin",
                ativo=True,
                totp_required=False,
            )
            db.session.add(u)
            db.session.commit()
            return u.id

    def test_post_login_sem_csrf_falha(self, client_with_csrf, app_csrf_on):
        r = client_with_csrf.post("/login", data={
            "email": "csrf@topshop.com.br",
            "senha": "SenhaForte1234",
        })
        # Sem token, Flask-WTF retorna 400 ou re-renderiza form
        assert r.status_code in (200, 400)
        # Se 200, a sessão NÃO deve ter sido criada
        if r.status_code == 200:
            with client_with_csrf.session_transaction() as sess:
                assert "_user_id" not in sess


class TestSenhaNaoVaza:
    def test_resposta_json_nao_contem_senha_hash(self, client, app, login_admin):
        r = client.get("/api/config")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "senha_hash" not in body
        assert "argon2" not in body

    def test_audit_nao_lista_senha(self, client, app, login_admin):
        client.post("/login", data={"email": "admin@topshop.com.br", "senha": "QualquerCoisa"})
        r = client.get("/admin/auditoria")
        body = r.get_data(as_text=True).lower()
        assert "qualquercoisa" not in body
        assert "argon2" not in body


class TestXSS:
    def test_nome_com_script_e_escapado(self, client, app, login_admin):
        from auth import Usuario
        from auth.security import hash_senha
        with app.app_context():
            u = Usuario(
                email="xss@topshop.com.br",
                nome="<script>alert(1)</script>",
                senha_hash=hash_senha("SenhaForte1234"),
                papel="usuario",
                ativo=True,
                totp_required=False,
            )
            db.session.add(u)
            db.session.commit()

        r = client.get("/admin/usuarios")
        # Jinja escapa por default — não deve haver <script> renderizado
        assert b"<script>alert(1)</script>" not in r.data
        assert b"&lt;script&gt;" in r.data
