"""Add created_at and updated_at to devices

Revision ID: 004
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy as sa

revision = '004'
down_revision = '9ce82bee6880'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('devices', sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.add_column('devices', sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))


def downgrade() -> None:
    op.drop_column('devices', 'updated_at')
    op.drop_column('devices', 'created_at')
