"""camera direction

Revision ID: 5ca0d6084eee
Revises: a3f9c2d81b44
Create Date: 2026-08-21 09:44:38.894904

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
 
 
revision = 'c92a6cdf7d3d'
down_revision = 'a3f9c2d81b44'
branch_labels = None
depends_on = None
 
 
def upgrade() -> None:
    camera_direction = postgresql.ENUM('entry', 'exit', name='camera_direction')
    camera_direction.create(op.get_bind())
 
    op.add_column(
        'CameraTABLE',
        sa.Column(
            'direction',
            postgresql.ENUM('entry', 'exit', name='camera_direction', create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        'CarTABLE',
        sa.Column(
            'direction',
            postgresql.ENUM('entry', 'exit', name='camera_direction', create_type=False),
            nullable=True,
        ),
    )
 
 
def downgrade() -> None:
    op.drop_column('CarTABLE', 'direction')
    op.drop_column('CameraTABLE', 'direction')
    postgresql.ENUM(name='camera_direction').drop(op.get_bind())
