"""contact

Revision ID: 25bf6331a93a
Revises: cde2bc295a2d
Create Date: 2026-08-27 16:59:06.000109

"""
from alembic import op
import sqlalchemy as sa


revision = '25bf6331a93a'
down_revision = 'cde2bc295a2d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        'ix_contacttable_user_content_type_unique',
        'ContactTABLE',
        ['user_id', 'content_type'],
        unique=True,
        postgresql_where=sa.text("content_type != 'other'"),
    )


def downgrade() -> None:
    op.drop_index('ix_contacttable_user_content_type_unique', table_name='ContactTABLE')