"""
Teste end-to-end real do fluxo de convite.

Sobe a aplicação Flask em memória (mesmo create_app que produção) e simula:
  1. Admin loga
  2. Admin gera convite via POST /admin/convites
  3. Logout
  4. Anônimo abre /registro/<token> (GET)
  5. Anônimo registra-se (POST)
  6. Verifica DB: usuário criado + convite marcado como usado
  7. Tenta reusar o link → 400

Diferente de pytest, este é um script standalone:
    python tests/test_e2e_convite.py
"""

from __future__ import annotations

import os
import sys
import tempfile

# Setup de paths/env igual ao conftest
_AQUI = os.path.dirname(os.path.abspath(__file__))
_SITE = os.path.dirname(_AQUI)
_RAIZ = os.path.dirname(_SITE)
for p in (_RAIZ, _SITE):
    if p not in sys.path:
        sys.path.insert(0, p)
os.chdir(_RAIZ)

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-e2e-secret-key-32bytes-fixed"
os.environ["ENV"] = "development"
os.environ["SESSION_COOKIE_SECURE"] = "0"

from auth import db, Usuario, Convite, EventoAuth  # noqa: E402
from auth.security import hash_senha  # noqa: E402
import web_app  # noqa: E402


PASS = 0
FAIL = 0


def check(nome: str, condicao: bool, detalhe: str = "") -> None:
    global PASS, FAIL
    if condicao:
        print(f"  OK  {nome}")
        PASS += 1
    else:
        msg = f"  FALHOU  {nome}"
        if detalhe:
            msg += f"  | {detalhe}"
        print(msg)
        FAIL += 1


def main() -> int:
    tmp_cfg = tempfile.mktemp(suffix=".json")
    os.environ.setdefault("APP_CONFIG_PATH", tmp_cfg)

    print("\n=== E2E Convite — fluxo completo ===\n")

    app = web_app.create_app({
        "TESTING": False,  # CSP/Talisman ativo (mais próximo de produção)
        "WTF_CSRF_ENABLED": False,  # facilita simular sem extrair token
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "RATELIMIT_ENABLED": False,
    })

    with app.app_context():
        db.create_all()
        admin = Usuario(
            email="admin@topshop.com.br",
            nome="Admin Master",
            senha_hash=hash_senha("SenhaForte123!"),
            papel="admin",
            ativo=True,
            totp_required=False,
        )
        db.session.add(admin)
        db.session.commit()

    client = app.test_client()

    # 1. Login admin
    print("[1] Login admin")
    r = client.post("/login", data={
        "email": "admin@topshop.com.br",
        "senha": "SenhaForte123!",
    })
    check("Login admin retorna 302", r.status_code == 302, f"status={r.status_code}")

    # 2. Admin gera convite
    print("\n[2] Admin gera convite")
    EMAIL_ALVO = "novo-usuario-e2e@topshop.com.br"
    r = client.post("/admin/convites", data={
        "email": EMAIL_ALVO,
        "papel": "usuario",
    })
    check("POST /admin/convites retorna 200", r.status_code == 200, f"status={r.status_code}")

    data = r.get_json() or {}
    check("Resposta inclui sucesso=true", data.get("sucesso") is True, str(data))
    check("Resposta inclui link", "link" in data and "/registro/" in data.get("link", ""), str(data.get("link")))
    check("Resposta inclui expira_horas=48", data.get("expira_horas") == 48)
    check("Resposta inclui email correto", data.get("email") == EMAIL_ALVO)

    link = data.get("link", "")
    # extrai token do link (formato http://localhost/registro/<token>)
    token = link.split("/registro/", 1)[-1]
    check("Token tem comprimento adequado (>40 chars)", len(token) > 40, f"len={len(token)}")

    # 3. Admin faz logout (registro deve ser anônimo)
    print("\n[3] Admin faz logout")
    r = client.post("/logout")
    check("Logout retorna 200/302", r.status_code in (200, 302))

    # 4. Anônimo abre o link
    print("\n[4] Anônimo abre /registro/<token>")
    r = client.get(f"/registro/{token}")
    check("GET /registro/<token> retorna 200", r.status_code == 200, f"status={r.status_code}")
    check("Página exibe email do convite", EMAIL_ALVO.encode() in r.data)

    # 5. Anônimo registra-se
    print("\n[5] Anônimo submete formulário")
    SENHA_NOVO = "SenhaUsuarioE2E1"
    r = client.post(
        f"/registro/{token}",
        data={
            "nome": "Usuário E2E",
            "senha": SENHA_NOVO,
            "confirmacao": SENHA_NOVO,
            # Tentativa de injeção: enviando email no form para ver se é ignorado
            "email": "atacante@evil.com",
            "papel": "admin",
        },
        follow_redirects=False,
    )
    check("POST /registro retorna 302 (logado)", r.status_code == 302, f"status={r.status_code}")

    # 6. Verifica DB
    print("\n[6] Verifica banco de dados")
    with app.app_context():
        u = db.session.query(Usuario).filter_by(email=EMAIL_ALVO).first()
        check("Usuário criado com email do convite", u is not None)
        if u:
            check("Papel do usuário = 'usuario' (não 'admin' do form)", u.papel == "usuario", f"papel={u.papel}")
            check("Usuário está ativo", u.ativo is True)
            check("Senha foi hasheada (não armazenada em texto)",
                  u.senha_hash and SENHA_NOVO not in u.senha_hash)

        # Convite marcado como usado
        c = db.session.query(Convite).filter_by(email=EMAIL_ALVO).first()
        check("Convite existe no banco", c is not None)
        if c:
            check("Convite tem usado_em preenchido", c.usado_em is not None)

        # Atacante NÃO foi criado
        atacante = db.session.query(Usuario).filter_by(email="atacante@evil.com").first()
        check("Email injetado no form foi ignorado (atacante não criado)", atacante is None)

        # Evento de auditoria
        ev = db.session.query(EventoAuth).filter_by(evento="convite_usado").first()
        check("Evento 'convite_usado' gravado em auditoria", ev is not None)

        ev_emit = db.session.query(EventoAuth).filter_by(evento="convite_emitido").first()
        check("Evento 'convite_emitido' gravado", ev_emit is not None)

    # 7. Tentar reusar o link
    print("\n[7] Tentar reusar o link já consumido")
    client.post("/logout")  # garante anônimo
    r = client.get(f"/registro/{token}")
    check("GET no token já usado retorna 400", r.status_code == 400, f"status={r.status_code}")

    # 8. Login com a conta criada
    print("\n[8] Login com a conta recém-criada")
    r = client.post("/login", data={
        "email": EMAIL_ALVO,
        "senha": SENHA_NOVO,
    })
    check("Login com nova conta retorna 302", r.status_code == 302, f"status={r.status_code}")

    # Limpa
    try:
        os.unlink(tmp_cfg)
    except Exception:
        pass

    print(f"\n=== Resultado: {PASS} passaram, {FAIL} falharam ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
