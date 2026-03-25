"""Add role classification columns

Revision ID: 003
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('devices', sa.Column('inferred_role', sa.String(50), nullable=True))
    op.add_column('devices', sa.Column('role_confidence', sa.Float(), nullable=True))
    op.add_column('devices', sa.Column('role_classified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('devices', sa.Column('role_classifier_version', sa.String(20), nullable=True))

def downgrade() -> None:
    op.drop_column('devices', 'role_classifier_version')
    op.drop_column('devices', 'role_classified_at')
    op.drop_column('devices', 'role_confidence')
    op.drop_column('devices', 'inferred_role')
