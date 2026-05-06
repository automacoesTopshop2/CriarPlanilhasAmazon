"""Testes de autenticação — login, logout, sessão, registro, reset."""

from __future__ import annotations

from datetime import timedelta

from auth import db, Usuario, Convite, EventoAuth, TokenReset
from auth.security import (
    hash_senha, verificar_senha, validar_forca_senha,
    gerar_token_url_safe, hash_token,
)
from auth.models import _utcnow


# =============================================================================
# Hashing
# =============================================================================
class TestHashSenha:
    def test_hash_argon2id(self):
        h = hash_senha("MinhaSenha12345")
        assert h.startswith("$argon2id$")

    def test_hash_diferente_a_cada_chamada(self):
        h1 = hash_senha("MesmaSenha123")
        h2 = hash_senha("MesmaSenha123")
        assert h1 != h2  # salt aleatório

    def test_verifica_correta(self):
        h = hash_senha("Senha-Forte-123")
        assert verificar_senha(h, "Senha-Forte-123") is True

    def test_verifica_incorreta(self):
        h = hash_senha("Senha-Forte-123")
        assert verificar_senha(h, "Senha-Errada") is False

    def test_verifica_sem_hash_armazenado(self):
        # Anti-enumeração: ainda executa argon2 dummy
        assert verificar_senha(None, "qualquer") is False

    def test_verifica_hash_invalido(self):
        assert verificar_senha("not-a-hash", "Senha-Forte-123") is False


class TestPoliticaSenha:
    def test_aceita_senha_forte(self):
        assert validar_forca_senha("MinhaSenha123") is None

    def test_rejeita_curta(self):
        msg = validar_forca_senha("Curta1")
        assert msg and "10" in msg

    def test_rejeita_sem_letra(self):
        assert "letra" in validar_forca_senha("1234567890123").lower()

    def test_rejeita_sem_numero(self):
        assert "número" in validar_forca_senha("SoLetraSenha").lower()

    def test_rejeita_vazia(self):
        assert validar_forca_senha("") is not None


# =============================================================================
# Login
# =============================================================================
class TestLogin:
    def test_get_login_anonimo(self, client):
        r = client.get("/login")
        assert r.status_code == 200
        assert b"Entrar" in r.data

    def test_login_feliz(self, client, app, admin):
        r = client.post(
            "/login",
            data={"email": "admin@topshop.com.br", "senha": "SenhaForte123!"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        # Sessão criada
        with client.session_transaction() as sess:
            assert "_user_id" in sess

    def test_login_redireciona_para_home(self, client, app, admin):
        r = client.post(
            "/login",
            data={"email": "admin@topshop.com.br", "senha": "SenhaForte123!"},
            follow_redirects=True,
        )
        assert r.status_code == 200
        assert b"Dashboard" in r.data or b"Topshop" in r.data

    def test_login_senha_errada(self, client, app, admin):
        r = client.post(
            "/login",
            data={"email": "admin@topshop.com.br", "senha": "SenhaErrada"},
        )
        assert r.status_code == 200  # mantém na página
        assert b"incorretos" in r.data
        # Audit log
        with app.app_context():
            ev = db.session.query(EventoAuth).filter_by(evento="login_falha").all()
            assert len(ev) == 1
            # contador incrementa
            u = db.session.query(Usuario).filter_by(email="admin@topshop.com.br").first()
            assert u.falhas_consecutivas == 1

    def test_login_email_inexistente(self, client, app):
        r = client.post(
            "/login",
            data={"email": "naoexiste@topshop.com.br", "senha": "qualquercoisa"},
        )
        assert r.status_code == 200
        assert b"incorretos" in r.data
        # Resposta genérica — mesma mensagem que senha errada
        with app.app_context():
            ev = db.session.query(EventoAuth).filter_by(evento="login_falha").all()
            assert len(ev) == 1

    def test_bloqueio_apos_5_falhas(self, client, app, admin):
        for _ in range(5):
            client.post(
                "/login",
                data={"email": "admin@topshop.com.br", "senha": "ErradaAA"},
            )
        with app.app_context():
            u = db.session.query(Usuario).filter_by(email="admin@topshop.com.br").first()
            assert u.falhas_consecutivas == 5
            assert u.esta_bloqueado is True
            ev = db.session.query(EventoAuth).filter_by(evento="bloqueio").count()
            assert ev == 1

    def test_login_durante_bloqueio_recusa_mesmo_com_senha_certa(self, client, app, admin):
        # Bloqueia
        for _ in range(5):
            client.post(
                "/login",
                data={"email": "admin@topshop.com.br", "senha": "ErradaAA"},
            )
        # Tenta com senha correta
        r = client.post(
            "/login",
            data={"email": "admin@topshop.com.br", "senha": "SenhaForte123!"},
        )
        assert b"bloqueada" in r.data.lower()

    def test_login_zera_contador_de_falhas(self, client, app, admin):
        client.post("/login", data={"email": "admin@topshop.com.br", "senha": "Errada"})
        client.post("/login", data={"email": "admin@topshop.com.br", "senha": "SenhaForte123!"})
        with app.app_context():
            u = db.session.query(Usuario).filter_by(email="admin@topshop.com.br").first()
            assert u.falhas_consecutivas == 0
            assert u.bloqueado_ate is None

    def test_usuario_desativado_nao_loga(self, client, app, usuario):
        with app.app_context():
            u = db.session.get(Usuario, usuario)
            u.ativo = False
            db.session.commit()
        r = client.post(
            "/login",
            data={"email": "user@topshop.com.br", "senha": "SenhaForte456@"},
        )
        assert b"incorretos" in r.data

    def test_login_grava_ultimo_login(self, client, app, admin):
        client.post(
            "/login",
            data={"email": "admin@topshop.com.br", "senha": "SenhaForte123!"},
        )
        with app.app_context():
            u = db.session.query(Usuario).filter_by(email="admin@topshop.com.br").first()
            assert u.ultimo_login is not None


# =============================================================================
# Logout
# =============================================================================
class TestLogout:
    def test_logout_invalida_sessao(self, client, login_admin):
        r = client.post("/logout")
        assert r.status_code == 302
        with client.session_transaction() as sess:
            assert "_user_id" not in sess

    def test_logout_anonimo_redireciona_login(self, client):
        r = client.post("/logout")
        assert r.status_code == 302  # via @login_required

    def test_logout_grava_audit(self, client, app, login_admin):
        client.post("/logout")
        with app.app_context():
            ev = db.session.query(EventoAuth).filter_by(evento="logout").count()
            assert ev == 1


# =============================================================================
# Convites e registro
# =============================================================================
class TestRegistro:
    def _criar_convite(self, app, email="novo@topshop.com.br", papel="usuario", ttl_h=48):
        token = gerar_token_url_safe()
        with app.app_context():
            c = Convite(
                email=email,
                papel=papel,
                token_hash=hash_token(token),
                expira_em=_utcnow() + timedelta(hours=ttl_h),
            )
            db.session.add(c)
            db.session.commit()
        return token

    def test_get_registro_token_valido(self, client, app):
        token = self._criar_convite(app)
        r = client.get(f"/registro/{token}")
        assert r.status_code == 200
        assert b"novo@topshop.com.br" in r.data

    def test_get_registro_token_invalido(self, client):
        r = client.get("/registro/token-fake-fake-fake")
        assert r.status_code == 400
        assert b"inv" in r.data.lower() or b"expirad" in r.data.lower()

    def test_post_registro_cria_usuario(self, client, app):
        token = self._criar_convite(app, email="zelda@topshop.com.br", papel="usuario")
        r = client.post(
            f"/registro/{token}",
            data={"nome": "Zelda Hyrule", "senha": "TriforceSagrada1", "confirmacao": "TriforceSagrada1"},
            follow_redirects=False,
        )
        assert r.status_code == 302
        with app.app_context():
            u = db.session.query(Usuario).filter_by(email="zelda@topshop.com.br").first()
            assert u is not None
            assert u.papel == "usuario"
            # convite marcado como usado
            c = db.session.query(Convite).first()
            assert c.usado_em is not None

    def test_registro_papel_admin_funciona(self, client, app):
        token = self._criar_convite(app, email="admin2@topshop.com.br", papel="admin")
        client.post(
            f"/registro/{token}",
            data={"nome": "Admin 2", "senha": "MasterSenha9991", "confirmacao": "MasterSenha9991"},
        )
        with app.app_context():
            u = db.session.query(Usuario).filter_by(email="admin2@topshop.com.br").first()
            assert u.papel == "admin"

    def test_registro_token_expirado(self, client, app):
        token = self._criar_convite(app, ttl_h=-1)
        r = client.get(f"/registro/{token}")
        assert r.status_code == 400

    def test_registro_token_ja_usado(self, client, app):
        token = self._criar_convite(app, email="link@topshop.com.br")
        client.post(
            f"/registro/{token}",
            data={"nome": "Link", "senha": "EspadaMestra123", "confirmacao": "EspadaMestra123"},
        )
        # Após registro o usuário fica logado — faz logout antes do segundo GET
        client.post("/logout")
        r = client.get(f"/registro/{token}")
        assert r.status_code == 400

    def test_registro_senha_fraca_recusada(self, client, app):
        token = self._criar_convite(app)
        r = client.post(
            f"/registro/{token}",
            data={"nome": "Teste", "senha": "fraca", "confirmacao": "fraca"},
        )
        # Form re-renderiza com erro
        assert r.status_code == 200

    def test_registro_senhas_diferentes(self, client, app):
        token = self._criar_convite(app)
        r = client.post(
            f"/registro/{token}",
            data={"nome": "Teste", "senha": "Senha-Forte-123", "confirmacao": "Outra-Coisa-456"},
        )
        assert r.status_code == 200

    def test_registro_grava_audit(self, client, app):
        token = self._criar_convite(app, email="auditado@topshop.com.br")
        client.post(
            f"/registro/{token}",
            data={"nome": "Audit", "senha": "AuditadoForte1", "confirmacao": "AuditadoForte1"},
        )
        with app.app_context():
            ev = db.session.query(EventoAuth).filter_by(evento="convite_usado").first()
            assert ev is not None

    def test_token_email_imutavel(self, client, app):
        """O email vem do CONVITE — campo 'email' enviado no form é ignorado."""
        token = self._criar_convite(app, email="vitima@topshop.com.br", papel="usuario")
        # Atacante tenta sobrescrever email com o do admin
        r = client.post(
            f"/registro/{token}",
            data={
                "email": "admin@topshop.com.br",  # tentativa de injeção
                "nome": "Atacante",
                "senha": "SenhaForteAttack1",
                "confirmacao": "SenhaForteAttack1",
            },
            follow_redirects=False,
        )
        assert r.status_code == 302
        with app.app_context():
            # Usuário foi criado com o email do CONVITE, não do form
            u = db.session.query(Usuario).filter_by(email="vitima@topshop.com.br").first()
            assert u is not None
            assert u.papel == "usuario"
            # Não criou usuário com email do admin
            adm = db.session.query(Usuario).filter_by(email="admin@topshop.com.br").first()
            assert adm is None


# =============================================================================
# Reset de senha
# =============================================================================
class TestReset:
    def _criar_token_reset(self, app, usuario_id, ttl_h=24):
        token = gerar_token_url_safe()
        with app.app_context():
            tr = TokenReset(
                usuario_id=usuario_id,
                token_hash=hash_token(token),
                expira_em=_utcnow() + timedelta(hours=ttl_h),
            )
            db.session.add(tr)
            db.session.commit()
        return token

    def test_reset_token_valido_troca_senha(self, client, app, usuario):
        token = self._criar_token_reset(app, usuario)
        r = client.post(
            f"/reset/{token}",
            data={"nova_senha": "NovaSenhaForte123", "confirmacao": "NovaSenhaForte123"},
        )
        assert r.status_code == 200
        # nova senha funciona
        with app.app_context():
            u = db.session.get(Usuario, usuario)
            assert verificar_senha(u.senha_hash, "NovaSenhaForte123")

    def test_reset_token_expirado(self, client, app, usuario):
        token = self._criar_token_reset(app, usuario, ttl_h=-1)
        r = client.get(f"/reset/{token}")
        assert r.status_code == 400

    def test_reset_token_invalido(self, client):
        r = client.get("/reset/inexistente-token")
        assert r.status_code == 400

    def test_reset_invalida_sessoes_antigas(self, client, app, usuario):
        with app.app_context():
            u = db.session.get(Usuario, usuario)
            versao_anterior = u.sessao_versao
        token = self._criar_token_reset(app, usuario)
        client.post(
            f"/reset/{token}",
            data={"nova_senha": "NovaSenhaForte123", "confirmacao": "NovaSenhaForte123"},
        )
        with app.app_context():
            u = db.session.get(Usuario, usuario)
            assert u.sessao_versao > versao_anterior


# =============================================================================
# Acesso protegido
# =============================================================================
class TestProtecao:
    def test_root_anonimo_redireciona(self, client):
        r = client.get("/", follow_redirects=False)
        assert r.status_code == 302
        assert "/login" in r.location

    def test_sku_anonimo_redireciona(self, client):
        r = client.get("/sku", follow_redirects=False)
        assert r.status_code == 302

    def test_api_anonimo_devolve_401(self, client):
        r = client.get("/api/bases")
        assert r.status_code == 401

    def test_admin_anonimo_redireciona(self, client):
        r = client.get("/admin/usuarios", follow_redirects=False)
        assert r.status_code == 302

    def test_configuracoes_anonimo_redireciona(self, client):
        r = client.get("/configuracoes", follow_redirects=False)
        assert r.status_code == 302

    def test_admin_como_usuario_comum_403(self, client, login_usuario):
        r = client.get("/admin/usuarios")
        assert r.status_code == 403

    def test_configuracoes_como_usuario_comum_403(self, client, login_usuario):
        r = client.get("/configuracoes")
        assert r.status_code == 403

    def test_admin_admin_200(self, client, login_admin):
        r = client.get("/admin/usuarios")
        assert r.status_code == 200

    def test_admin_dashboard_200(self, client, login_usuario):
        r = client.get("/")
        assert r.status_code == 200


# =============================================================================
# Sessão e sessao_versao
# =============================================================================
class TestSessaoVersao:
    def test_versao_invalidada_nao_carrega_usuario(self, client, app, login_usuario):
        # Aumenta sessao_versao manualmente
        with app.app_context():
            u = db.session.get(Usuario, login_usuario)
            u.sessao_versao += 1
            db.session.commit()
        # Próximo request deve dar 302/401
        r = client.get("/api/bases")
        assert r.status_code == 401
