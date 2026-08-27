"""email

Revision ID: dec0b6cd309e
Revises: fa22800b9348
Create Date: 2026-08-27 14:01:59.574483

"""
from alembic import op
import sqlalchemy as sa


revision = 'dec0b6cd309e'
down_revision = 'fa22800b9348'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE verify_type ADD VALUE IF NOT EXISTS 'EMAIL_CHANGE'")


def downgrade() -> None:
    raise NotImplementedError(
        "postgres does not support dropping enum values directly; "
        "downgrading verify_type requires manually recreating the type"
    )