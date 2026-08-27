"""profile

Revision ID: cde2bc295a2d
Revises: 04677021af0d
Create Date: 2026-08-27 16:06:33.378284

"""
from alembic import op
import sqlalchemy as sa


revision = 'cde2bc295a2d'
down_revision = '04677021af0d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('UserTABLE', sa.Column('avatar_path', sa.String(length=255), nullable=True))

def downgrade() -> None:
    op.drop_column('UserTABLE', 'avatar_path')