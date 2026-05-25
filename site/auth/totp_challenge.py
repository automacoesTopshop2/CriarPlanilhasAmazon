"""
Temp token + state do desafio 2FA entre /login e /login/verify-2fa.

Por que dupla camada (token assinado + linha em desafios_2fa):
    - Token assinado (itsdangerous): impede forja — sem SECRET_KEY o atacante
      não consegue fabricar um id válido.
    - Tabela desafios_2fa: guarda state mutável (consumido_em, tentativas_falhas)
      que não cabe no token; também permite invalidação server-side
      (lockout após N falhas, expiração explícita por hora-do-banco, etc.).
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Optional, Tuple

from flask import current_app, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .models import DesafioDoisFatores, Usuario, db, _utcnow


PROPOSITO_VERIFICACAO = "verificacao"     # usuário já tem 2FA — só digitar o código
PROPOSITO_ENROLLMENT = "enrollment"        # usuário precisa configurar 2FA

MAX_TENTATIVAS = 5
SALT_TEMP_TOKEN = "topshop-2fa-temp-token"


def _ttl_segundos() -> int:
    try:
        return int(os.getenv("TOTP_CHALLENGE_TTL_SECONDS", "300"))
    except ValueError:
        return 300


def _serializer() -> URLSafeTimedSerializer:
    secret = current_app.config.get("SECRET_KEY")
    if not secret:
        raise RuntimeError("SECRET_KEY ausente — temp_token não pode ser assinado.")
    return URLSafeTimedSerializer(secret, salt=SALT_TEMP_TOKEN)


def _client_ip() -> Optional[str]:
    cf = request.headers.get("CF-Connecting-IP")
    if cf:
        return cf
    return request.remote_addr


def _client_ua() -> Optional[str]:
    return (request.headers.get("User-Agent") or "")[:500] or None


# =============================================================================
# Criação
# =============================================================================
def criar_desafio(
    usuario: Usuario,
    proposito: str,
    *,
    lembrar: bool = False,
) -> Tuple[str, DesafioDoisFatores]:
    """
    Cria registro em desafios_2fa + emite temp_token assinado.

    `proposito` ∈ {PROPOSITO_VERIFICACAO, PROPOSITO_ENROLLMENT}.
    Retorna (temp_token, desafio).
    """
    if proposito not in (PROPOSITO_VERIFICACAO, PROPOSITO_ENROLLMENT):
        raise ValueError(f"propósito inválido: {proposito}")

    ttl = _ttl_segundos()
    desafio = DesafioDoisFatores(
        usuario_id=usuario.id,
        proposito=proposito,
        expira_em=_utcnow() + timedelta(seconds=ttl),
        tentativas_falhas=0,
        lembrar=bool(lembrar),
        ip=_client_ip(),
        user_agent=_client_ua(),
    )
    db.session.add(desafio)
    db.session.commit()

    # token = {id, proposito} assinado. id é UUID; ainda assim quebrar pra
    # incluir proposito permite validação dupla (token x banco).
    token = _serializer().dumps({"jti": desafio.id, "p": proposito})
    return token, desafio


# =============================================================================
# Decodificação / validação
# =============================================================================
class DesafioInvalido(Exception):
    """temp_token inválido, expirado, consumido ou propósito errado."""


def carregar_desafio(
    temp_token: str,
    proposito_esperado: str,
) -> Tuple[DesafioDoisFatores, Usuario]:
    """
    Decodifica token, valida ttl, busca o desafio no banco. Não consome.

    Levanta DesafioInvalido em qualquer falha (assinatura, expirado, consumido,
    propósito divergente, lockout).
    """
    if not temp_token:
        raise DesafioInvalido("temp_token ausente")
    try:
        dados = _serializer().loads(temp_token, max_age=_ttl_segundos())
    except SignatureExpired:
        raise DesafioInvalido("expirado")
    except BadSignature:
        raise DesafioInvalido("assinatura inválida")

    if not isinstance(dados, dict):
        raise DesafioInvalido("payload inesperado")
    jti = dados.get("jti")
    p = dados.get("p")
    if not jti or p != proposito_esperado:
        raise DesafioInvalido("propósito divergente")

    desafio = db.session.get(DesafioDoisFatores, jti)
    if not desafio:
        raise DesafioInvalido("desafio não encontrado")
    if desafio.proposito != proposito_esperado:
        raise DesafioInvalido("propósito do registro divergente")
    if desafio.consumido_em is not None:
        raise DesafioInvalido("desafio já consumido")
    if desafio.esta_expirado:
        raise DesafioInvalido("expirado")
    if desafio.tentativas_falhas >= MAX_TENTATIVAS:
        raise DesafioInvalido("muitas tentativas")

    usuario = db.session.get(Usuario, desafio.usuario_id)
    if not usuario or not usuario.ativo:
        raise DesafioInvalido("usuário inválido")

    return desafio, usuario


def registrar_falha(desafio: DesafioDoisFatores) -> None:
    """Incrementa contador de falhas e faz commit."""
    desafio.tentativas_falhas = (desafio.tentativas_falhas or 0) + 1
    db.session.commit()


def consumir_desafio(desafio: DesafioDoisFatores) -> None:
    """Marca o desafio como consumido (uso único)."""
    desafio.consumido_em = _utcnow()
    db.session.commit()
