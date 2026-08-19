"""add notification table

Revision ID: a3f9c2d81b44
Revises: 8e2a91f4c7b6
Create Date: 2026-08-19 09:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = 'a3f9c2d81b44'
down_revision = '8e2a91f4c7b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'NotificationTABLE',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('village_id', sa.UUID(), nullable=True),
        sa.Column('action', sa.String(length=255), nullable=False),
        sa.Column('detail', sa.String(length=1000), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_read', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['UserTABLE.id'], name=op.f('fk_NotificationTABLE_user_id_UserTABLE'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['village_id'], ['GroupTABLE.id'], name=op.f('fk_NotificationTABLE_village_id_GroupTABLE'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_NotificationTABLE')),
    )
    op.create_index(op.f('ix_NotificationTABLE_user_id'), 'NotificationTABLE', ['user_id'], unique=False)
    op.create_index(op.f('ix_NotificationTABLE_created_at'), 'NotificationTABLE', ['created_at'], unique=False)
    op.create_index(
        'ix_notificationtable_user_unread_created',
        'NotificationTABLE',
        ['user_id', 'is_read', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_notificationtable_user_unread_created', table_name='NotificationTABLE')
    op.drop_index(op.f('ix_NotificationTABLE_created_at'), table_name='NotificationTABLE')
    op.drop_index(op.f('ix_NotificationTABLE_user_id'), table_name='NotificationTABLE')
    op.drop_table('NotificationTABLE')