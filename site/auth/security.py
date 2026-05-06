"""
Funções de segurança: hashing, tokens, validações e decorators.

Hashing:
    Argon2id (argon2-cffi). Padrão atual recomendado por OWASP.
    Verificação inclui execução em "dummy" quando o usuário não existe,
    garantindo tempo de resposta uniforme (anti-enumeração de e-mails).

Tokens:
    secrets.token_urlsafe(32) — 256 bits de entropia.
    Armazenados como SHA-256 hex no banco; valor cru só vai pelo link uma vez.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from datetime import datetime, timezone
from functools import wraps
from typing import Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError, VerificationError
from flask import abort, current_app, request
from flask_login import current_user

from .models import EventoAuth, db


# Hasher único na aplicação. Parâmetros conservadores para Argon2id:
# time_cost=3, memory_cost=64MB, parallelism=4 (recomendado OWASP 2023+).
_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)

# Hash dummy gerado uma vez para usar em verificações "vazias" (anti-enum).
_DUMMY_HASH = _HASHER.hash("password-anti-enumeration-dummy-string")


# =============================================================================
# Senhas
# =============================================================================
def hash_senha(senha: str) -> str:
    return _HASHER.hash(senha)


def verificar_senha(hash_armazenado: Optional[str], senha: str) -> bool:
    """
    Verifica senha contra hash armazenado.
    Sempre executa argon2.verify (mesmo se hash_armazenado for None) para
    manter tempo de resposta constante (mitigar enumeração de e-mails).
    """
    if not hash_armazenado:
        try:
            _HASHER.verify(_DUMMY_HASH, senha)
        except (VerifyMismatchError, InvalidHashError, VerificationError):
            pass
        return False

    try:
        _HASHER.verify(hash_armazenado, senha)
        return True
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


_RE_LETRA = re.compile(r"[A-Za-z]")
_RE_NUMERO = re.compile(r"[0-9]")


def validar_forca_senha(senha: str) -> Optional[str]:
    """
    Retorna mensagem de erro se a senha for fraca, ou None se OK.
    Política: ≥10 chars, ao menos 1 letra e 1 número.
    """
    if not senha or len(senha) < 10:
        return "A senha deve ter ao menos 10 caracteres."
    if not _RE_LETRA.search(senha):
        return "A senha deve conter ao menos uma letra."
    if not _RE_NUMERO.search(senha):
        return "A senha deve conter ao menos um número."
    return None


# =============================================================================
# Tokens
# =============================================================================
def gerar_token_url_safe(nbytes: int = 32) -> str:
    """Token aleatório criptograficamente seguro."""
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """SHA-256 hex — usado para armazenar convites/tokens-reset no banco."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# =============================================================================
# Decorators
# =============================================================================
def requer_admin(view_func):
    """Garante que current_user é admin. 401 se anon, 403 se comum."""
    @wraps(view_func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            abort(401)
        if not getattr(current_user, "is_admin", False):
            abort(403)
        return view_func(*args, **kwargs)
    return wrapper


# =============================================================================
# Audit log
# =============================================================================
def _ip_real() -> Optional[str]:
    """
    IP real do cliente. Atrás de Cloudflare, usa CF-Connecting-IP.
    Atrás de proxy reverso confiável, usa X-Forwarded-For (já tratado pelo
    ProxyFix antes do request chegar aqui).
    """
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf
    return request.remote_addr


def registrar_evento(
    evento: str,
    usuario_id: Optional[str] = None,
    email_tentado: Optional[str] = None,
    detalhes: Optional[str] = None,
) -> None:
    """Insere uma linha em eventos_auth. Tolerante a falhas (não derruba request)."""
    try:
        ev = EventoAuth(
            usuario_id=usuario_id,
            email_tentado=(email_tentado or "").lower().strip() or None,
            evento=evento,
            detalhes=detalhes,
            ip=_ip_real(),
            user_agent=(request.headers.get("User-Agent") or "")[:500],
        )
        db.session.add(ev)
        db.session.commit()
    except Exception as e:  # pragma: no cover
        try:
            db.session.rollback()
        except Exception:
            pass
        # Fallback estruturado: garante que o evento fique rastreável mesmo
        # se o banco estiver indisponível. Formato chave=valor para facilitar
        # parsing por agregadores de log.
        try:
            ip_fallback = _ip_real()
        except Exception:
            ip_fallback = None
        current_app.logger.error(
            "AUDIT_FAIL evento=%s usuario=%s email=%s ip=%s detalhes=%s erro=%s",
            evento,
            usuario_id or "-",
            (email_tentado or "-"),
            ip_fallback or "-",
            (detalhes or "-"),
            e,
        )


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()
