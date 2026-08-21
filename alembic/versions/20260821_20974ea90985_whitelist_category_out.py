"""Whitelist Category out

Revision ID: 20974ea90985
Revises: c92a6cdf7d3d
Create Date: 2026-08-21 13:14:11.545516

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
 
 
revision = '9d3b1f2a6e7c'
down_revision = 'c92a6cdf7d3d'
branch_labels = None
depends_on = None
 
 
def upgrade() -> None:
    op.add_column('WhitelistTABLE', sa.Column('house_no', sa.String(length=255), nullable=True))
    op.add_column('WhitelistTABLE', sa.Column('phone', sa.String(length=20), nullable=True))
    op.add_column('WhitelistTABLE', sa.Column('color', sa.String(length=255), nullable=True))
    op.drop_column('WhitelistTABLE', 'category')
    postgresql.ENUM(name='whitelist_category').drop(op.get_bind())
 
 
def downgrade() -> None:
    whitelist_category = postgresql.ENUM('resident', 'regular', 'guest', name='whitelist_category')
    whitelist_category.create(op.get_bind())
    op.add_column('WhitelistTABLE', sa.Column('category', whitelist_category, nullable=True))
    op.drop_column('WhitelistTABLE', 'color')
    op.drop_column('WhitelistTABLE', 'phone')
    op.drop_column('WhitelistTABLE', 'house_no')
