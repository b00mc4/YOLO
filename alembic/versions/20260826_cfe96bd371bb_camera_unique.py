"""camera unique

Revision ID: cfe96bd371bb
Revises: 5ffcf3a95123
Create Date: 2026-08-26 09:16:57.672668

"""
from alembic import op
import sqlalchemy as sa


revision = 'cfe96bd371bb'
down_revision = '5ffcf3a95123'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        op.f('uq_CameraTABLE_stream_ai'), 'CameraTABLE', ['stream_ai']
    )
 
 
def downgrade() -> None:
    op.drop_constraint(
        op.f('uq_CameraTABLE_stream_ai'), 'CameraTABLE', type_='unique'
    )

