"""add_internal_camera_direction

Revision ID: d518624090bb
Revises: d011635287bd
Create Date: 2026-09-01 17:25:52.039338

"""
from alembic import op
import sqlalchemy as sa


revision = 'd518624090bb'
down_revision = 'd011635287bd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("COMMIT")
    op.execute("ALTER TYPE camera_direction ADD VALUE 'internal'")


def downgrade() -> None:
    pass
