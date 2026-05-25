"""
Serviço TOTP — encapsula pyotp + Fernet + tabelas de backup codes.

Fluxos:
    1. Enrollment:
         gerar_secret_pendente(usuario)
            → salva pending no banco + retorna URI/QR para o app authenticator
         confirmar_2fa(usuario, codigo)
            → valida código contra pending → promove para ativo + gera backup codes
    2. Verificação no login:
         verificar_codigo(usuario, codigo)
            → tenta TOTP primeiro, depois backup code (consome se válido)
    3. Desativação:
         desabilitar_2fa(usuario) → limpa todos os campos
"""

from __future__ import annotations

import base64
import io
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import pyotp
import qrcode

from .models import CodigoBackup2FA, Usuario, db, _utcnow
from .security import hash_token
from .totp_crypto import decrypt_totp_secret, encrypt_totp_secret


PENDENTE_TTL_MIN = 10
QTD_BACKUP_CODES = 10
BACKUP_CODE_BYTES = 8   # → 16 hex chars → "XXXX-XXXX-XXXX-XXXX"


def _issuer() -> str:
    return (os.getenv("TOTP_ISSUER") or "CriarPlanilhasAmazon").strip()


def _valid_window() -> int:
    try:
        return int(os.getenv("TOTP_VALID_WINDOW", "1"))
    except ValueError:
        return 1


# =============================================================================
# Geração de secret e QR
# =============================================================================
def gerar_secret_pendente(usuario: Usuario) -> Tuple[str, str, str]:
    """
    Gera um novo secret pendente para o usuário, salva no banco (criptografado)
    e devolve (secret_base32, otpauth_uri, qr_png_base64).

    O secret só vira "ativo" após confirmar_2fa() — antes disso fica em
    totp_secret_pending_encrypted e expira em PENDENTE_TTL_MIN.
    """
    secret = pyotp.random_base32()
    usuario.totp_secret_pending_encrypted = encrypt_totp_secret(secret)
    usuario.totp_pending_expires_at = _utcnow() + timedelta(minutes=PENDENTE_TTL_MIN)
    db.session.commit()

    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=usuario.email,
        issuer_name=_issuer(),
    )
    qr_b64 = _gerar_qr_base64(uri)
    return secret, uri, qr_b64


def _gerar_qr_base64(uri: str) -> str:
    """Gera PNG base64 (data URI ready) do QR code."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# =============================================================================
# Confirmação do enrollment
# =============================================================================
def _pending_valido(usuario: Usuario) -> bool:
    if not usuario.totp_secret_pending_encrypted or not usuario.totp_pending_expires_at:
        return False
    exp = usuario.totp_pending_expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    return exp > _utcnow()


def confirmar_2fa(usuario: Usuario, codigo: str) -> bool:
    """
    Valida o código contra o secret pendente. Em caso de sucesso:
    - promove pending → ativo
    - marca enrolled_at
    - regenera backup codes

    Retorna True se válido (commit feito), False se inválido (sem commit).
    """
    if not _pending_valido(usuario):
        return False

    try:
        secret = decrypt_totp_secret(usuario.totp_secret_pending_encrypted)
    except Exception:
        return False

    totp = pyotp.TOTP(secret)
    if not totp.verify(_normalizar_codigo(codigo), valid_window=_valid_window()):
        return False

    # promove
    usuario.totp_secret_encrypted = usuario.totp_secret_pending_encrypted
    usuario.totp_secret_pending_encrypted = None
    usuario.totp_pending_expires_at = None
    usuario.totp_enabled = True
    usuario.totp_enrolled_at = _utcnow()
    db.session.commit()
    return True


def regenerar_backup_codes(usuario: Usuario) -> List[str]:
    """
    Apaga backup codes anteriores e gera 10 novos.
    Retorna os códigos em texto claro — devem ser exibidos UMA vez.
    """
    db.session.query(CodigoBackup2FA).filter_by(usuario_id=usuario.id).delete()
    codigos: List[str] = []
    for _ in range(QTD_BACKUP_CODES):
        cru = secrets.token_hex(BACKUP_CODE_BYTES).upper()       # 16 hex chars
        formatado = "-".join(cru[i:i + 4] for i in range(0, 16, 4))
        codigos.append(formatado)
        db.session.add(CodigoBackup2FA(
            usuario_id=usuario.id,
            codigo_hash=hash_token(cru),   # normalizado sem hífens
        ))
    db.session.commit()
    return codigos


# =============================================================================
# Verificação no login
# =============================================================================
_RE_OTP = re.compile(r"\D+")


def _normalizar_codigo(codigo: str) -> str:
    """Remove espaços, hífens, etc. — facilita paste do app autenticador."""
    return _RE_OTP.sub("", (codigo or "")).strip()


def _normalizar_backup(codigo: str) -> str:
    """Backup code: tira hífens e força uppercase. Tudo HEX (0-9 A-F)."""
    return (codigo or "").replace("-", "").replace(" ", "").upper().strip()


def verificar_codigo(usuario: Usuario, codigo_bruto: str) -> bool:
    """
    Verifica código TOTP ou de backup. Consome o backup se for o caso.
    Retorna True/False. Não loga eventos — chamador faz isso.
    """
    if not usuario.totp_enabled or not usuario.totp_secret_encrypted:
        return False

    codigo = (codigo_bruto or "").strip()
    if not codigo:
        return False

    # 1) TOTP (6 dígitos)
    so_digitos = _normalizar_codigo(codigo)
    if len(so_digitos) == 6 and so_digitos.isdigit():
        try:
            secret = decrypt_totp_secret(usuario.totp_secret_encrypted)
        except Exception:
            return False
        totp = pyotp.TOTP(secret)
        if totp.verify(so_digitos, valid_window=_valid_window()):
            return True

    # 2) Backup code (16 hex chars depois de normalizar)
    bk = _normalizar_backup(codigo)
    if len(bk) == 16 and all(c in "0123456789ABCDEF" for c in bk):
        h = hash_token(bk)
        registro = (
            db.session.query(CodigoBackup2FA)
            .filter_by(usuario_id=usuario.id, codigo_hash=h, usado_em=None)
            .first()
        )
        if registro:
            registro.usado_em = _utcnow()
            db.session.commit()
            return True

    return False


def codigos_backup_restantes(usuario: Usuario) -> int:
    return (
        db.session.query(CodigoBackup2FA)
        .filter_by(usuario_id=usuario.id, usado_em=None)
        .count()
    )


# =============================================================================
# Desativação
# =============================================================================
def desabilitar_2fa(usuario: Usuario) -> None:
    """Limpa todos os campos 2FA e descarta backup codes."""
    usuario.totp_secret_encrypted = None
    usuario.totp_secret_pending_encrypted = None
    usuario.totp_pending_expires_at = None
    usuario.totp_enabled = False
    usuario.totp_enrolled_at = None
    db.session.query(CodigoBackup2FA).filter_by(usuario_id=usuario.id).delete()
    db.session.commit()
