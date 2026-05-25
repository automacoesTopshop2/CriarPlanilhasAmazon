"""
Criptografia simétrica (Fernet) para o secret TOTP do usuário.

Em vez de gravar o secret base32 do TOTP em claro no banco, criptografamos
com uma chave mantida em env (TOTP_ENCRYPTION_KEY). Banco vazado sem a
chave ainda inutiliza os secrets — sem chave, código não roda em prod.

Rotação:
    Trocar TOTP_ENCRYPTION_KEY invalida todos os secrets gravados (vai
    falhar no decrypt). Isso força re-enrollment dos usuários — comportamento
    intencional para rotação emergencial.
"""

from __future__ import annotations

import os
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


class TOTPCryptoError(RuntimeError):
    """Erro de configuração ou decrypt do secret TOTP."""


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    chave = (os.getenv("TOTP_ENCRYPTION_KEY") or "").strip()
    if not chave:
        raise TOTPCryptoError(
            "TOTP_ENCRYPTION_KEY não configurada. "
            "Gere com: python -c \"from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(chave.encode("ascii"))
    except (ValueError, TypeError) as e:
        raise TOTPCryptoError(
            f"TOTP_ENCRYPTION_KEY inválida (precisa ser uma Fernet key de 32 bytes "
            f"base64-encoded): {e}"
        ) from e


def encrypt_totp_secret(secret: str) -> bytes:
    """Encripta o secret TOTP (base32) para gravar no banco."""
    if not secret:
        raise ValueError("secret vazio")
    return _fernet().encrypt(secret.encode("utf-8"))


def decrypt_totp_secret(blob: bytes) -> str:
    """Decripta o secret TOTP. Levanta TOTPCryptoError se a chave mudou."""
    if not blob:
        raise TOTPCryptoError("blob vazio (secret ausente)")
    try:
        return _fernet().decrypt(blob).decode("utf-8")
    except InvalidToken as e:
        # Chave rotacionada, secret corrompido ou registro de outro ambiente.
        raise TOTPCryptoError(
            "Falha ao decriptar secret TOTP — chave possivelmente rotacionada. "
            "Usuário precisa re-enrolar 2FA."
        ) from e


def reset_cache_para_testes() -> None:
    """Limpa o cache do Fernet — útil em testes que injetam env diferente."""
    _fernet.cache_clear()
