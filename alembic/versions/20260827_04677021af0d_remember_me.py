"""remember me

Revision ID: 04677021af0d
Revises: aad40b9cf836
Create Date: 2026-08-27 15:14:10.303696

"""
from alembic import op
import sqlalchemy as sa


revision = '04677021af0d'
down_revision = 'aad40b9cf836'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'RefreshTABLE',
        sa.Column('remember_me', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    )


def downgrade() -> None:
    op.drop_column('RefreshTABLE', 'remember_me')