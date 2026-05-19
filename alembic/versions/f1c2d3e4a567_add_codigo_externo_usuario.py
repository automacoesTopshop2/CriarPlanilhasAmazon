"""adiciona codigo_externo ao usuario para integração BDAmazon

Revision ID: f1c2d3e4a567
Revises: e44b06c264c5
Create Date: 2026-05-19 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1c2d3e4a567'
down_revision = 'e44b06c264c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('codigo_externo', sa.String(length=64), nullable=True)
        )
        batch_op.create_index(
            batch_op.f('ix_usuarios_codigo_externo'),
            ['codigo_externo'],
            unique=True,
        )


def downgrade() -> None:
    with op.batch_alter_table('usuarios', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_usuarios_codigo_externo'))
        batch_op.drop_column('codigo_externo')
