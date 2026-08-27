"""password

Revision ID: aad40b9cf836
Revises: dec0b6cd309e
Create Date: 2026-08-27 14:44:31.428148

"""
from alembic import op
import sqlalchemy as sa


revision = 'aad40b9cf836'
down_revision = 'dec0b6cd309e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'UserTABLE',
        sa.Column('password_changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    )

def downgrade() -> None:
    op.drop_column('UserTABLE', 'password_changed_at')
