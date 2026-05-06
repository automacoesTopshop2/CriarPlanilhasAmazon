"""
Bootstrap do usuário master.

Uso:
    python site/auth/bootstrap_master.py
    -- ou --
    python -m site.auth.bootstrap_master

Ações:
    1. Cria as tabelas se não existirem (via SQLAlchemy create_all — ok para dev).
       Em produção use Alembic upgrade.
    2. Recusa se já existir admin (não cria duplicidade).
    3. Pede e-mail, nome e senha (com confirmação).
    4. Valida força de senha.
    5. Insere com papel='admin'.
"""

from __future__ import annotations

import getpass
import os
import sys

# Garante que a raiz do projeto está em sys.path quando rodado direto
_AQUI = os.path.dirname(os.path.abspath(__file__))
_RAIZ = os.path.dirname(os.path.dirname(_AQUI))
if _RAIZ not in sys.path:
    sys.path.insert(0, _RAIZ)
os.chdir(_RAIZ)


def main() -> int:
    # Importações tardias para garantir sys.path correto
    from flask import Flask

    from auth.models import Usuario, db
    from auth.security import hash_senha, normalizar_email, validar_forca_senha

    # Mini-app só pra ter contexto SQLAlchemy
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "sqlite:///auth.db"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()

        existe_admin = (
            db.session.query(Usuario).filter_by(papel="admin", ativo=True).first()
        )
        if existe_admin:
            print(f"[ABORTADO] Já existe um administrador ativo: {existe_admin.email}")
            print("Use a interface /admin/usuarios para gerenciar.")
            return 1

        print("=" * 60)
        print("BOOTSTRAP DO USUÁRIO MASTER (Topshop Amazon System)")
        print("=" * 60)

        email = input("E-mail do master: ").strip().lower()
        if not email or "@" not in email:
            print("E-mail inválido.")
            return 2

        ja_existe = db.session.query(Usuario).filter_by(email=email).first()
        if ja_existe:
            print(f"Já existe um usuário com esse e-mail (papel={ja_existe.papel}).")
            return 3

        nome = input("Nome: ").strip()
        if len(nome) < 2:
            print("Nome muito curto.")
            return 4

        while True:
            senha = getpass.getpass("Senha (>= 10 chars, com letra e número): ")
            erro = validar_forca_senha(senha)
            if erro:
                print(f"  -> {erro}")
                continue
            confirmacao = getpass.getpass("Confirmar senha: ")
            if senha != confirmacao:
                print("  -> As senhas não conferem.")
                continue
            break

        usuario = Usuario(
            email=normalizar_email(email),
            nome=nome,
            senha_hash=hash_senha(senha),
            papel="admin",
            ativo=True,
        )
        db.session.add(usuario)
        db.session.commit()

        print()
        print("=" * 60)
        print(f"OK — master criado: {usuario.email}")
        print("Acesse: http://127.0.0.1:5000/login")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
