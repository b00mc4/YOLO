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
    op.add_column('CarTABLE', sa.Column('village_id', sa.UUID(), nullable=True))
    op.add_column('CarTABLE', sa.Column('camera_name', sa.String(length=255), nullable=True))
    op.add_column('CarTABLE', sa.Column('camera_lat', sa.Float(precision=53), nullable=True))
    op.add_column('CarTABLE', sa.Column('camera_long', sa.Float(precision=53), nullable=True))
 
    op.create_index(op.f('ix_CarTABLE_village_id'), 'CarTABLE', ['village_id'], unique=False)
    op.create_foreign_key(
        op.f('fk_CarTABLE_village_id_GroupTABLE'),
        'CarTABLE', 'GroupTABLE', ['village_id'], ['id'], ondelete='SET NULL',
    )
 
    op.execute(
        """
        UPDATE "CarTABLE"
        SET village_id = c.village_id,
            camera_name = c.name,
            camera_lat = c.lat,
            camera_long = c.long
        FROM "CameraTABLE" c
        WHERE "CarTABLE".camera_id = c.id
        """
    )
 
    op.alter_column('CarTABLE', 'camera_id', existing_type=sa.UUID(), nullable=True)
 
    op.drop_constraint(
        op.f('fk_CarTABLE_camera_id_CameraTABLE'), 'CarTABLE', type_='foreignkey'
    )
    op.create_foreign_key(
        op.f('fk_CarTABLE_camera_id_CameraTABLE'),
        'CarTABLE', 'CameraTABLE', ['camera_id'], ['id'], ondelete='SET NULL',
    )
 
 
def downgrade() -> None:
    op.drop_constraint(
        op.f('fk_CarTABLE_camera_id_CameraTABLE'), 'CarTABLE', type_='foreignkey'
    )
    op.create_foreign_key(
        op.f('fk_CarTABLE_camera_id_CameraTABLE'),
        'CarTABLE', 'CameraTABLE', ['camera_id'], ['id'],
    )
    op.alter_column('CarTABLE', 'camera_id', existing_type=sa.UUID(), nullable=False)
 
    op.drop_constraint(
        op.f('fk_CarTABLE_village_id_GroupTABLE'), 'CarTABLE', type_='foreignkey'
    )
    op.drop_index(op.f('ix_CarTABLE_village_id'), table_name='CarTABLE')
    op.drop_column('CarTABLE', 'camera_long')
    op.drop_column('CarTABLE', 'camera_lat')
    op.drop_column('CarTABLE', 'camera_name')
    op.drop_column('CarTABLE', 'village_id')
