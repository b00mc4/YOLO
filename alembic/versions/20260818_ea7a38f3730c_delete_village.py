"""Delete Village

Revision ID: ea7a38f3730c
Revises: 1c1e4ae7996b
Create Date: 2026-08-18 10:42:23.866706

"""
from alembic import op
import sqlalchemy as sa
 
 
revision = '8e2a91f4c7b6'
down_revision = '1c1e4ae7996b'
branch_labels = None
depends_on = None
 
 
def upgrade() -> None:
    op.drop_constraint(
        op.f('fk_AuditLogTABLE_village_id_GroupTABLE'), 'AuditLogTABLE', type_='foreignkey'
    )
    op.create_foreign_key(
        op.f('fk_AuditLogTABLE_village_id_GroupTABLE'),
        'AuditLogTABLE', 'GroupTABLE', ['village_id'], ['id'], ondelete='SET NULL',
    )
 
 
def downgrade() -> None:
    op.drop_constraint(
        op.f('fk_AuditLogTABLE_village_id_GroupTABLE'), 'AuditLogTABLE', type_='foreignkey'
    )
    op.create_foreign_key(
        op.f('fk_AuditLogTABLE_village_id_GroupTABLE'),
        'AuditLogTABLE', 'GroupTABLE', ['village_id'], ['id'],
    )
