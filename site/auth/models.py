"""
Modelos SQLAlchemy para autenticação, autorização e auditoria.

Compatível com PostgreSQL (produção) e SQLite (dev/testes) via SQLAlchemy.
Em Postgres: usa CITEXT para email e UUID nativo. Em SQLite: cai para String.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

db = SQLAlchemy()


def _utcnow() -> datetime:
    """UTC com timezone — evita confusão entre dev (sqlite) e prod (postgres)."""
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


# =============================================================================
# Usuario
# =============================================================================
class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    senha_hash: Mapped[str] = mapped_column(Text, nullable=False)
    papel: Mapped[str] = mapped_column(String(20), nullable=False, default="usuario")  # 'admin' | 'usuario'
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    ultimo_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    falhas_consecutivas: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bloqueado_ate: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # versão da sessão — incrementar invalida todas as sessões ativas do usuário
    sessao_versao: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # ---- helpers ----

    @property
    def is_admin(self) -> bool:
        return self.papel == "admin"

    @property
    def esta_bloqueado(self) -> bool:
        if not self.bloqueado_ate:
            return False
        agora = _utcnow()
        bloq = self.bloqueado_ate
        if bloq.tzinfo is None:
            # SQLite às vezes devolve naive — tratamos como UTC
            bloq = bloq.replace(tzinfo=timezone.utc)
        return bloq > agora

    def get_id(self) -> str:
        # Flask-Login usa get_id para serializar — incluímos sessao_versao
        # para que mudanças invalidem sessões antigas.
        return f"{self.id}:{self.sessao_versao}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Usuario {self.email} ({self.papel})>"


# =============================================================================
# Convite (e-mail + token armazenado como hash)
# =============================================================================
class Convite(db.Model):
    __tablename__ = "convites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    papel: Mapped[str] = mapped_column(String(20), nullable=False, default="usuario")
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    criado_por: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("usuarios.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    criador = relationship("Usuario", foreign_keys=[criado_por])

    @property
    def esta_expirado(self) -> bool:
        agora = _utcnow()
        exp = self.expira_em
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= agora

    @property
    def esta_usado(self) -> bool:
        return self.usado_em is not None

    @property
    def esta_valido(self) -> bool:
        return not self.esta_usado and not self.esta_expirado


# =============================================================================
# Token de reset de senha (mesma mecânica do convite)
# =============================================================================
class TokenReset(db.Model):
    __tablename__ = "tokens_reset"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_uuid)
    usuario_id: Mapped[str] = mapped_column(String(36), ForeignKey("usuarios.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    usado_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    usuario = relationship("Usuario")

    @property
    def esta_expirado(self) -> bool:
        agora = _utcnow()
        exp = self.expira_em
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return exp <= agora

    @property
    def esta_valido(self) -> bool:
        return self.usado_em is None and not self.esta_expirado


# =============================================================================
# Evento de auditoria
# =============================================================================
class EventoAuth(db.Model):
    __tablename__ = "eventos_auth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("usuarios.id"), nullable=True)
    email_tentado: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    evento: Mapped[str] = mapped_column(String(50), nullable=False)
    detalhes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)

    usuario = relationship("Usuario")
