"""
Testes do fluxo 2FA TOTP:
    - Login com 2FA habilitado (sucesso/falha/expirado)
    - Enrollment forçado quando totp_required && !totp_enabled
    - Backup code uso único
    - Bypass quando totp_required=false
    - Lockout após N tentativas falhas
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone

import pyotp
import pytest

from auth import db, Usuario, CodigoBackup2FA, DesafioDoisFatores
from auth.models import _utcnow
from auth.security import hash_senha, hash_token
from auth.totp_crypto import encrypt_totp_secret
from auth import totp_challenge, totp_service


SECRET_FIXO = "JBSWY3DPEHPK3PXP"   # base32 conhecido p/ reprodutibilidade


def _gerar_otp(secret: str = SECRET_FIXO) -> str:
    """Gera o código TOTP corrente para o secret."""
    return pyotp.TOTP(secret).now()


# =============================================================================
# Login com 2FA HABILITADO
# =============================================================================
class TestLoginCom2FA:
    def test_login_com_senha_certa_emite_desafio_e_nao_seta_sessao(
        self, client, app, usuario_2fa
    ):
        r = client.post("/login", data={
            "email": usuario_2fa["email"],
            "senha": usuario_2fa["senha"],
        })
        # Renderiza o template de verificação (200), sem redirect
        assert r.status_code == 200
        assert b"verificar-2fa" in r.data or "Código".encode("utf-8") in r.data
        # Sessão NÃO foi criada
        with client.session_transaction() as sess:
            assert "_user_id" not in sess
        # Desafio gravado
        with app.app_context():
            d = db.session.query(DesafioDoisFatores).filter_by(
                usuario_id=usuario_2fa["id"]
            ).first()
            assert d is not None
            assert d.proposito == totp_challenge.PROPOSITO_VERIFICACAO
            assert d.consumido_em is None

    def test_verifica_codigo_correto_loga_e_consome_desafio(
        self, client, app, usuario_2fa
    ):
        r = client.post("/login", data={
            "email": usuario_2fa["email"],
            "senha": usuario_2fa["senha"],
        })
        temp_token = _extrair_temp_token(r.data)
        assert temp_token

        r2 = client.post("/login/verificar-2fa", data={
            "temp_token": temp_token,
            "codigo": _gerar_otp(usuario_2fa["secret"]),
        }, follow_redirects=False)
        assert r2.status_code == 302
        with client.session_transaction() as sess:
            assert "_user_id" in sess
        # Desafio consumido
        with app.app_context():
            d = db.session.query(DesafioDoisFatores).filter_by(
                usuario_id=usuario_2fa["id"]
            ).first()
            assert d.consumido_em is not None

    def test_verifica_codigo_errado_incrementa_falhas_e_mantem_desafio(
        self, client, app, usuario_2fa
    ):
        r = client.post("/login", data={
            "email": usuario_2fa["email"],
            "senha": usuario_2fa["senha"],
        })
        temp_token = _extrair_temp_token(r.data)

        r2 = client.post("/login/verificar-2fa", data={
            "temp_token": temp_token,
            "codigo": "000000",   # provável que esteja errado (não é o atual)
        })
        # Pode raramente coincidir; protege com retry. Mas SECRET_FIXO é
        # determinístico: o "now" depende do clock real. Se coincidir, a
        # janela ±1 ainda só permite código corrente±30s, então "000000"
        # tem ~1/1e6 chance.
        assert r2.status_code == 200
        with client.session_transaction() as sess:
            assert "_user_id" not in sess
        with app.app_context():
            d = db.session.query(DesafioDoisFatores).filter_by(
                usuario_id=usuario_2fa["id"]
            ).first()
            assert d.tentativas_falhas == 1
            assert d.consumido_em is None

    def test_lockout_apos_5_falhas(self, client, app, usuario_2fa):
        r = client.post("/login", data={
            "email": usuario_2fa["email"],
            "senha": usuario_2fa["senha"],
        })
        temp_token = _extrair_temp_token(r.data)

        # 5 falhas
        for _ in range(5):
            client.post("/login/verificar-2fa", data={
                "temp_token": temp_token,
                "codigo": "000000",
            })
        # 6ª tentativa: mesmo com código correto, deve ser rejeitada
        r2 = client.post("/login/verificar-2fa", data={
            "temp_token": temp_token,
            "codigo": _gerar_otp(usuario_2fa["secret"]),
        })
        assert r2.status_code == 200
        with client.session_transaction() as sess:
            assert "_user_id" not in sess

    def test_temp_token_de_outro_proposito_e_rejeitado(self, client, app, usuario_2fa):
        # Cria um desafio de ENROLLMENT manualmente e tenta usar em /verificar-2fa
        with app.test_request_context("/"):
            u = db.session.get(Usuario, usuario_2fa["id"])
            token, _ = totp_challenge.criar_desafio(
                u, totp_challenge.PROPOSITO_ENROLLMENT
            )
        r = client.post("/login/verificar-2fa", data={
            "temp_token": token,
            "codigo": _gerar_otp(usuario_2fa["secret"]),
        })
        # Renderiza com fatal=True
        assert r.status_code == 200
        with client.session_transaction() as sess:
            assert "_user_id" not in sess


# =============================================================================
# Backup codes
# =============================================================================
class TestBackupCodes:
    def test_backup_code_funciona_e_uso_unico(self, client, app, usuario_2fa):
        # Gera 1 backup code manualmente
        with app.app_context():
            u = db.session.get(Usuario, usuario_2fa["id"])
            codigos = totp_service.regenerar_backup_codes(u)
        cru = codigos[0]   # formato XXXX-XXXX-XXXX-XXXX

        # 1ª tentativa: aceita
        r = client.post("/login", data={
            "email": usuario_2fa["email"], "senha": usuario_2fa["senha"],
        })
        temp_token = _extrair_temp_token(r.data)
        r2 = client.post("/login/verificar-2fa", data={
            "temp_token": temp_token, "codigo": cru,
        })
        assert r2.status_code == 302
        # Verifica que o código está marcado como usado
        with app.app_context():
            registro = db.session.query(CodigoBackup2FA).filter_by(
                codigo_hash=hash_token(cru.replace("-", ""))
            ).first()
            assert registro is not None
            assert registro.usado_em is not None

        # Logout
        client.post("/logout")

        # 2ª tentativa com o mesmo código: falha
        r3 = client.post("/login", data={
            "email": usuario_2fa["email"], "senha": usuario_2fa["senha"],
        })
        temp_token2 = _extrair_temp_token(r3.data)
        r4 = client.post("/login/verificar-2fa", data={
            "temp_token": temp_token2, "codigo": cru,
        })
        assert r4.status_code == 200
        with client.session_transaction() as sess:
            assert "_user_id" not in sess


# =============================================================================
# Enrollment forçado quando totp_required && !totp_enabled
# =============================================================================
class TestEnrollmentForcado:
    def test_login_com_required_sem_enabled_redireciona_para_configurar(
        self, client, app
    ):
        # Cria usuário precisa configurar 2FA
        with app.app_context():
            u = Usuario(
                email="precisa@topshop.com.br",
                nome="Precisa Configurar",
                senha_hash=hash_senha("SenhaForte123!"),
                papel="usuario",
                ativo=True,
                totp_required=True,
                totp_enabled=False,
            )
            db.session.add(u)
            db.session.commit()

        r = client.post("/login", data={
            "email": "precisa@topshop.com.br",
            "senha": "SenhaForte123!",
        }, follow_redirects=False)
        assert r.status_code == 302
        assert "/2fa/configurar" in r.headers["Location"]
        # Não logado
        with client.session_transaction() as sess:
            assert "_user_id" not in sess

    def test_enrollment_completo_loga_o_usuario(self, client, app):
        with app.app_context():
            u = Usuario(
                email="enroll@topshop.com.br",
                nome="Enroll User",
                senha_hash=hash_senha("SenhaForte123!"),
                papel="usuario",
                ativo=True,
                totp_required=True,
                totp_enabled=False,
            )
            db.session.add(u)
            db.session.commit()

        # POST /login → redirect /2fa/configurar?t=...
        r = client.post("/login", data={
            "email": "enroll@topshop.com.br",
            "senha": "SenhaForte123!",
        }, follow_redirects=False)
        loc = r.headers["Location"]
        m = re.search(r"t=([^&]+)", loc)
        assert m, f"temp_token não encontrado em {loc}"
        temp_token = m.group(1)

        # GET /2fa/configurar?t=... → gera secret pendente
        r2 = client.get(f"/2fa/configurar?t={temp_token}")
        assert r2.status_code == 200

        # Pega o secret base32 da página (está dentro de div.secret-box)
        m_secret = re.search(rb'<div class="secret-box">([A-Z2-7]+)</div>', r2.data)
        assert m_secret, "secret não encontrado no template enrollment"
        secret = m_secret.group(1).decode()

        # POST /2fa/configurar com código válido
        codigo = pyotp.TOTP(secret).now()
        r3 = client.post("/2fa/configurar", data={
            "t": temp_token,
            "codigo": codigo,
        })
        # Renderiza tela de backup codes
        assert r3.status_code == 200
        assert b"backup" in r3.data.lower() or b"c\xc3\xb3digos" in r3.data.lower()
        # Sessão criada
        with client.session_transaction() as sess:
            assert "_user_id" in sess
        # Banco: totp_enabled=True
        with app.app_context():
            u = db.session.query(Usuario).filter_by(
                email="enroll@topshop.com.br"
            ).first()
            assert u.totp_enabled is True
            assert u.totp_secret_encrypted is not None
            # 10 backup codes gerados
            n = db.session.query(CodigoBackup2FA).filter_by(usuario_id=u.id).count()
            assert n == 10


# =============================================================================
# Bypass (totp_required=False)
# =============================================================================
class TestBypass:
    def test_usuario_sem_required_e_sem_enabled_loga_direto(self, client, app):
        # `usuario` fixture já tem totp_required=False
        with app.app_context():
            u = Usuario(
                email="bypass@topshop.com.br",
                nome="Bypass User",
                senha_hash=hash_senha("SenhaForte123!"),
                papel="usuario",
                ativo=True,
                totp_required=False,
                totp_enabled=False,
            )
            db.session.add(u)
            db.session.commit()

        r = client.post("/login", data={
            "email": "bypass@topshop.com.br",
            "senha": "SenhaForte123!",
        }, follow_redirects=False)
        assert r.status_code == 302
        # Vai direto pra home (não pro enrollment)
        assert "/2fa/configurar" not in r.headers.get("Location", "")
        with client.session_transaction() as sess:
            assert "_user_id" in sess


# =============================================================================
# Verificação de código (serviço)
# =============================================================================
class TestVerificarCodigo:
    def test_aceita_codigo_corrente(self, app):
        with app.app_context():
            u = Usuario(
                email="v@topshop.com.br", nome="V", senha_hash=hash_senha("x" * 12),
                papel="usuario", ativo=True,
                totp_required=False, totp_enabled=True,
                totp_secret_encrypted=encrypt_totp_secret(SECRET_FIXO),
            )
            db.session.add(u); db.session.commit()
            assert totp_service.verificar_codigo(u, _gerar_otp()) is True

    def test_rejeita_codigo_aleatorio(self, app):
        with app.app_context():
            u = Usuario(
                email="v2@topshop.com.br", nome="V", senha_hash=hash_senha("x" * 12),
                papel="usuario", ativo=True,
                totp_required=False, totp_enabled=True,
                totp_secret_encrypted=encrypt_totp_secret(SECRET_FIXO),
            )
            db.session.add(u); db.session.commit()
            assert totp_service.verificar_codigo(u, "123456") is False

    def test_normaliza_espacos_e_hifens(self, app):
        with app.app_context():
            u = Usuario(
                email="v3@topshop.com.br", nome="V", senha_hash=hash_senha("x" * 12),
                papel="usuario", ativo=True,
                totp_required=False, totp_enabled=True,
                totp_secret_encrypted=encrypt_totp_secret(SECRET_FIXO),
            )
            db.session.add(u); db.session.commit()
            cod = _gerar_otp()
            # insere espaços/separadores
            cod_sujo = f"{cod[:3]} {cod[3:]}"
            assert totp_service.verificar_codigo(u, cod_sujo) is True


# =============================================================================
# Helpers
# =============================================================================
def _extrair_temp_token(html: bytes) -> str:
    """Lê o value do <input name="temp_token"> no HTML renderizado."""
    m = re.search(rb'name="temp_token"\s+type="hidden"\s+value="([^"]+)"', html)
    if not m:
        # WTForms pode renderizar com ordem diferente: <input ... type=hidden ... value=...>
        m = re.search(rb'name="temp_token"[^>]*value="([^"]+)"', html)
    if not m:
        m = re.search(rb'value="([^"]+)"[^>]*name="temp_token"', html)
    assert m, "temp_token não encontrado no HTML retornado"
    return m.group(1).decode()
