"""
Initial migration - Create all tables from models
"""

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def upgrade():
    """Upgrade database to latest schema."""
    
    # Create all tables based on the current models
    op.create_table(
        'organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('settings', postgresql.JSONB, default=dict),
        sa.Column('parent_org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='SET NULL')),
        sa.Column('is_msp', sa.Boolean, default=False),
        sa.Column('subscription_tier', sa.String(length=50), default='starter'),
        sa.Column('max_devices', sa.Integer, default=25),
        sa.Column('feature_flags', postgresql.JSONB, default=dict),
        sa.Column('billing_cycle_start', sa.DateTime(timezone=True)),
        sa.Column('data_retention_days', sa.Integer, default=90),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.Index('idx_organizations_parent_org_id', 'parent_org_id'),
        sa.Index('idx_organizations_is_msp', 'is_msp'),
        sa.Index('idx_organizations_subscription_tier', 'subscription_tier'),
    )
    
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255)),
        sa.Column('role', sa.String(length=50), default='viewer'),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('last_login', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.Index('idx_users_organization_id', 'organization_id'),
        sa.Index('idx_users_email', 'email'),
        sa.Index('idx_users_role', 'role'),
        sa.UniqueConstraint('email', name='uq_users_email'),
    )
    
    op.create_table(
        'devices',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scan_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('scans.id', ondelete='SET NULL')),
        sa.Column('hostname', sa.String(length=255)),
        sa.Column('ip_address', postgresql.INET, nullable=False),
        sa.Column('mac_address', postgresql.MACADDR),
        sa.Column('vendor', sa.String(length=100)),
        sa.Column('model', sa.String(length=100)),
        sa.Column('os_type', sa.String(length=50)),
        sa.Column('os_version', sa.String(length=100)),
        sa.Column('device_type', sa.String(length=50)),
        sa.Column('device_role', sa.String(length=50)),
        sa.Column('serial_number', sa.String(length=100)),
        sa.Column('location', sa.String(length=255)),
        sa.Column('compliance_scope', postgresql.JSONB, default=list),
        sa.Column('metadata', postgresql.JSONB, default=dict),
        sa.Column('discovered_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('site_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sites.id', ondelete='SET NULL')),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('local_agents.id', ondelete='SET NULL')),
        sa.Column('role_vector', postgresql.ARRAY(sa.Float), postgresql_using='vector'),
        sa.Column('topology_vector', postgresql.ARRAY(sa.Float), postgresql_using='vector'),
        sa.Column('security_vector', postgresql.ARRAY(sa.Float), postgresql_using='vector'),
        sa.Column('config_vector', postgresql.ARRAY(sa.Float), postgresql_using='vector'),
        sa.Index('idx_devices_organization_id', 'organization_id'),
        sa.Index('idx_devices_ip_address', 'ip_address'),
        sa.Index('idx_devices_mac_address', 'mac_address'),
        sa.Index('idx_devices_hostname', 'hostname'),
        sa.Index('idx_devices_vendor', 'vendor'),
        sa.Index('idx_devices_device_type', 'device_type'),
        sa.Index('idx_devices_last_seen', 'last_seen'),
        sa.Index('idx_devices_site_id', 'site_id'),
        sa.Index('idx_devices_agent_id', 'agent_id'),
        sa.Index('idx_devices_compliance_scope', 'compliance_scope', postgresql_using='gin'),
        sa.Index('uq_devices_org_ip_active', 'organization_id', 'ip_address', postgresql_where=sa.text('is_active = true'), unique=True),
    )
    
    op.create_table(
        'interfaces',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('devices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('mac_address', postgresql.MACADDR),
        sa.Column('ip_address', postgresql.INET),
        sa.Column('subnet_mask', postgresql.INET),
        sa.Column('status', sa.String(length=20), default='unknown'),
        sa.Column('admin_status', sa.String(length=20), default='unknown'),
        sa.Column('speed', sa.Integer),
        sa.Column('duplex', sa.String(length=20)),
        sa.Column('mtu', sa.Integer),
        sa.Column('vlan_id', sa.Integer),
        sa.Column('metadata', postgresql.JSONB, default=dict),
        sa.Column('discovered_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('last_seen', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Index('idx_interfaces_device_id', 'device_id'),
        sa.Index('idx_interfaces_name', 'name'),
        sa.Index('idx_interfaces_ip_address', 'ip_address'),
        sa.Index('idx_interfaces_mac_address', 'mac_address'),
        sa.Index('idx_interfaces_vlan_id', 'vlan_id'),
        sa.Index('idx_interfaces_status', 'status'),
    )
    
    op.create_table(
        'discoveries',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('targets', postgresql.JSONB, nullable=False),
        sa.Column('scan_profile', sa.String(length=50), default='standard'),
        sa.Column('status', sa.String(length=50), default='pending'),
        sa.Column('progress', sa.Integer, default=0),
        sa.Column('results', postgresql.JSONB, default=dict),
        sa.Column('error_message', sa.Text),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.Index('idx_discoveries_organization_id', 'organization_id'),
        sa.Index('idx_discoveries_created_by', 'created_by'),
        sa.Index('idx_discoveries_status', 'status'),
        sa.Index('idx_discoveries_created_at', 'created_at'),
    )
    
    op.create_table(
        'scans',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('discovery_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('discoveries.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scan_type', sa.String(length=50), nullable=False),
        sa.Column('target', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), default='pending'),
        sa.Column('results', postgresql.JSONB, default=dict),
        sa.Column('error_message', sa.Text),
        sa.Column('started_at', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.Index('idx_scans_discovery_id', 'discovery_id'),
        sa.Index('idx_scans_scan_type', 'scan_type'),
        sa.Index('idx_scans_status', 'status'),
        sa.Index('idx_scans_target', 'target'),
    )
    
    op.create_table(
        'configurations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('device_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('devices.id', ondelete='CASCADE'), nullable=False),
        sa.Column('config_type', sa.String(length=50), default='running'),
        sa.Column('config_hash', sa.String(length=64), nullable=False),
        sa.Column('metadata_diff', postgresql.JSONB, default=dict),
        sa.Column('captured_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('captured_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.Index('idx_configurations_device_id', 'device_id'),
        sa.Index('idx_configurations_config_hash', 'config_hash'),
        sa.Index('idx_configurations_captured_at', 'captured_at'),
    )
    
    op.create_table(
        'credentials',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('username', sa.String(length=255), nullable=False),
        sa.Column('encrypted_password', sa.Text, nullable=False),
        sa.Column('credential_type', sa.String(length=50), nullable=False),
        sa.Column('target_filter', postgresql.JSONB, default=dict),
        sa.Column('metadata', postgresql.JSONB, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.Index('idx_credentials_organization_id', 'organization_id'),
        sa.Index('idx_credentials_credential_type', 'credential_type'),
    )
    
    op.create_table(
        'sites',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('site_type', sa.String(length=50), default='on_premises'),
        sa.Column('location_address', sa.String(length=500)),
        sa.Column('timezone', sa.String(length=100), default='UTC'),
        sa.Column('metadata', postgresql.JSONB, default=dict),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.UniqueConstraint('organization_id', 'name', name='uq_sites_org_name'),
        sa.Index('idx_sites_organization_id', 'organization_id'),
        sa.Index('idx_sites_site_type', 'site_type'),
    )
    
    op.create_table(
        'local_agents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('site_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sites.id', ondelete='SET NULL')),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('api_key_hash', sa.String(length=255), nullable=False),
        sa.Column('agent_version', sa.String(length=50)),
        sa.Column('last_seen', sa.DateTime(timezone=True)),
        sa.Column('last_ip', sa.String(length=45)),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('capabilities', postgresql.JSONB, default=dict),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), onupdate=sa.text('now()')),
        sa.UniqueConstraint('organization_id', 'name', name='uq_local_agents_org_name'),
        sa.Index('idx_local_agents_organization_id', 'organization_id'),
        sa.Index('idx_local_agents_site_id', 'site_id'),
        sa.Index('idx_local_agents_is_active', 'is_active'),
        sa.Index('idx_local_agents_last_seen', 'last_seen'),
    )
    
    op.create_table(
        'audit_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text('gen_random_uuid()')),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL')),
        sa.Column('agent_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('local_agents.id', ondelete='SET NULL')),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=50)),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True)),
        sa.Column('resource_name', sa.String(length=255)),
        sa.Column('outcome', sa.String(length=20), default='success'),
        sa.Column('details', postgresql.JSONB, default=dict),
        sa.Column('ip_address', sa.String(length=45)),
        sa.Column('user_agent', sa.String(length=500)),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Index('idx_audit_logs_organization_id', 'organization_id'),
        sa.Index('idx_audit_logs_user_id', 'user_id'),
        sa.Index('idx_audit_logs_agent_id', 'agent_id'),
        sa.Index('idx_audit_logs_action', 'action'),
        sa.Index('idx_audit_logs_resource_type_id', 'resource_type', 'resource_id'),
    )
    
    # Create pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade():
    """Downgrade database to previous schema."""
    
    # Drop tables in reverse order to respect foreign key constraints
    op.drop_table('audit_logs')
    op.drop_table('local_agents')
    op.drop_table('sites')
    op.drop_table('credentials')
    op.drop_table('configurations')
    op.drop_table('scans')
    op.drop_table('discoveries')
    op.drop_table('interfaces')
    op.drop_table('devices')
    op.drop_table('users')
    op.drop_table('organizations')
    
    # Drop pgvector extension
    op.execute("DROP EXTENSION IF EXISTS vector")