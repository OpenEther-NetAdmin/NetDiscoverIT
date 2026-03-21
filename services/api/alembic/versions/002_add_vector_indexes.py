"""
Add HNSW vector indexes for Device embeddings
"""

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    """Create HNSW vector indexes for Device embeddings."""
    
    # HNSW indexes for the 4 Device vector columns.
    # HNSW is preferred over IVFFlat for 768-dim embeddings: better recall (95-99%),
    # no training phase, supports live inserts, and consistent performance.
    # m=16 (graph connections per layer), ef_construction=64 (build-time quality).
    # Cosine similarity matches sentence-transformer / text-embedding output space.
    hnsw_indexes = [
        ("idx_devices_role_vector",     "role_vector"),
        ("idx_devices_topology_vector", "topology_vector"),
        ("idx_devices_security_vector", "security_vector"),
        ("idx_devices_config_vector",   "config_vector"),
    ]
    
    for idx_name, column in hnsw_indexes:
        op.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} "
            f"ON devices USING hnsw ({column} vector_cosine_ops) "
            f"WITH (m = 16, ef_construction = 64)"
        )


def downgrade():
    """Drop HNSW vector indexes."""
    
    indexes = [
        "idx_devices_role_vector",
        "idx_devices_topology_vector",
        "idx_devices_security_vector",
        "idx_devices_config_vector",
    ]
    
    for idx in indexes:
        op.execute(f"DROP INDEX IF EXISTS {idx}")