"""adiciona 2FA TOTP: colunas em usuarios + codigos_backup_2fa + desafios_2fa

Revision ID: a8b2c3d4e5f6
Revises: f1c2d3e4a567
Create Date: 2026-05-25 12:00:00.000000

"""
import os

from alembic import op
import sqlalchemy as sa


revision = 'a8b2c3d4e5f6'
down_revision = 'f1c2d3e4a567'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # usuarios: novas colunas 2FA
    # ------------------------------------------------------------------
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(sa.Column('totp_secret_encrypted', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('totp_secret_pending_encrypted', sa.LargeBinary(), nullable=True))
        batch_op.add_column(sa.Column('totp_pending_expires_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column(
            'totp_enabled', sa.Boolean(), nullable=False, server_default=sa.false()
        ))
        batch_op.add_column(sa.Column('totp_enrolled_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column(
            'totp_required', sa.Boolean(), nullable=False, server_default=sa.true()
        ))

    # Backfill: emails em TOTP_BYPASS_EMAILS recebem totp_required=false.
    # Pré-existentes ficam com server_default=true (precisam configurar 2FA).
    bypass_raw = os.getenv('TOTP_BYPASS_EMAILS', '') or ''
    bypass_emails = [
        e.strip().lower() for e in bypass_raw.split(',') if e.strip()
    ]
    if bypass_emails:
        conn = op.get_bind()
        # parametrizado para evitar SQL injection caso o env venha sujo
        conn.execute(
            sa.text("UPDATE usuarios SET totp_required = :v WHERE LOWER(email) IN :emails")
            .bindparams(sa.bindparam('emails', expanding=True)),
            {'v': False, 'emails': bypass_emails},
        )

    # ------------------------------------------------------------------
    # codigos_backup_2fa
    # ------------------------------------------------------------------
    op.create_table(
        'codigos_backup_2fa',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('usuario_id', sa.String(length=36), nullable=False),
        sa.Column('codigo_hash', sa.String(length=128), nullable=False),
        sa.Column('usado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('codigos_backup_2fa', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_codigos_backup_2fa_usuario_id'),
            ['usuario_id'],
            unique=False,
        )

    # ------------------------------------------------------------------
    # desafios_2fa
    # ------------------------------------------------------------------
    op.create_table(
        'desafios_2fa',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('usuario_id', sa.String(length=36), nullable=False),
        sa.Column('proposito', sa.String(length=20), nullable=False),
        sa.Column('criado_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expira_em', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumido_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('tentativas_falhas', sa.SmallInteger(), nullable=False, server_default='0'),
        sa.Column('lembrar', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('ip', sa.String(length=64), nullable=True),
        sa.Column('user_agent', sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(['usuario_id'], ['usuarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('desafios_2fa', schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f('ix_desafios_2fa_usuario_id'),
            ['usuario_id'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('desafios_2fa', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_desafios_2fa_usuario_id'))
    op.drop_table('desafios_2fa')

    with op.batch_alter_table('codigos_backup_2fa', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_codigos_backup_2fa_usuario_id'))
    op.drop_table('codigos_backup_2fa')

    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_column('totp_required')
        batch_op.drop_column('totp_enrolled_at')
        batch_op.drop_column('totp_enabled')
        batch_op.drop_column('totp_pending_expires_at')
        batch_op.drop_column('totp_secret_pending_encrypted')
        batch_op.drop_column('totp_secret_encrypted')
