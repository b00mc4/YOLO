"""add delay to camera

Revision ID: a1b2c3d4e5f6
Revises: e5fea52599ec
Create Date: 2026-09-14 09:58:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = 'e5fea52599ec'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('CameraTABLE', sa.Column('delay', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('CameraTABLE', 'delay')

