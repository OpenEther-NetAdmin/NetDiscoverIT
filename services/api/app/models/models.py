"""
Database Models - PostgreSQL
Based on net-discit database-schemas.md
"""

from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, ForeignKey,
    TypeDecorator, UniqueConstraint, Index, func, inet, macaddr, text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()

# ---------------------------------------------------------------------------
# Fernet-based encrypted text column
# ---------------------------------------------------------------------------
_fernet = None


def _get_fernet():
    """Lazily initialise Fernet from settings (avoids circular import at module load)."""
    global _fernet
    if _fernet is None:
        from cryptography.fernet import Fernet
        from app.core.config import settings
        _fernet = Fernet(settings.CREDENTIAL_ENCRYPTION_KEY.encode())
    return _fernet


class EncryptedText(TypeDecorator):
    """
    Transparent AES-128-CBC + HMAC-SHA256 encryption via cryptography.fernet.
    Values are encrypted before being written to the DB and decrypted on read.
    """
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return _get_fernet().encrypt(value.encode()).decode()
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            return _get_fernet().decrypt(value.encode()).decode()
        return value


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class Organization(Base):
    """Organization model"""
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    settings = Column(JSONB, default=dict)
    # Per-org API key for local agent authentication (stored as bcrypt hash — never plaintext).
    # The local agent sends X-Agent-Key: <plaintext>; middleware hashes and compares.
    agent_api_key_hash = Column(String(255))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="organization", cascade="all, delete-orphan")
    discoveries = relationship("Discovery", back_populates="organization", cascade="all, delete-orphan")
    credentials = relationship("Credential", back_populates="organization", cascade="all, delete-orphan")
    integrations = relationship("IntegrationConfig", back_populates="organization", cascade="all, delete-orphan")


class User(Base):
    """User model"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(String(50), default="viewer")  # admin, editor, viewer
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="users")

    __table_args__ = (
        Index("idx_users_organization_id", "organization_id"),
        Index("idx_users_email", "email"),
        Index("idx_users_role", "role"),
    )


class Device(Base):
    """Device model"""
    __tablename__ = "devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    scan_id = Column(UUID(as_uuid=True), ForeignKey("scans.id", ondelete="SET NULL"))
    hostname = Column(String(255))
    ip_address = Column(inet, nullable=False)
    mac_address = Column(macaddr)
    vendor = Column(String(100))
    model = Column(String(100))
    os_type = Column(String(50))
    os_version = Column(String(100))
    device_type = Column(String(50))  # router, switch, firewall, wireless, server, unknown
    device_role = Column(String(50))  # core, distribution, access, etc.
    serial_number = Column(String(100))
    location = Column(String(255))
    # Compliance scope tags — which regulatory frameworks this device is in scope for.
    # Used to generate audit-ready documentation on demand (PCI, HIPAA, SOX, etc.).
    # Values: "PCI-CDE", "PCI-BOUNDARY", "HIPAA-PHI", "SOX-FINANCIAL", "FEDRAMP-BOUNDARY",
    #         "ISO27001", "SOC2", "NIST-CSF" — multiple allowed.
    # Set by customer during onboarding or device classification; updated by ML role classifier.
    compliance_scope = Column(JSONB, default=list)  # e.g. ["PCI-CDE", "HIPAA-PHI"]
    metadata = Column(JSONB, default=dict)
    discovered_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)

    # ML vector embeddings (768-dim, populated by the vectorizer pipeline)
    # Used for: semantic search, role classification, topology similarity, RAG
    role_vector = Column(Vector(768))      # device functional role fingerprint
    topology_vector = Column(Vector(768))  # network position and connectivity
    security_vector = Column(Vector(768))  # security posture
    config_vector = Column(Vector(768))    # configuration similarity search

    # Relationships
    organization = relationship("Organization", back_populates="devices")
    interfaces = relationship("Interface", back_populates="device", cascade="all, delete-orphan")
    configurations = relationship("Configuration", back_populates="device", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_devices_organization_id", "organization_id"),
        Index("idx_devices_ip_address", "ip_address"),
        Index("idx_devices_mac_address", "mac_address"),
        Index("idx_devices_hostname", "hostname"),
        Index("idx_devices_vendor", "vendor"),
        Index("idx_devices_device_type", "device_type"),
        Index("idx_devices_last_seen", "last_seen"),
        Index("idx_devices_compliance_scope", "compliance_scope", postgresql_using="gin"),
        # Partial unique index: only one active record per org+IP pair
        UniqueConstraint(
            "organization_id", "ip_address",
            name="uq_devices_org_ip_active",
            postgresql_where=text("is_active = true"),
        ),
    )


class Interface(Base):
    """Interface model"""
    __tablename__ = "interfaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    mac_address = Column(macaddr)
    ip_address = Column(inet)
    subnet_mask = Column(inet)
    status = Column(String(20), default="unknown")       # up, down, testing, unknown
    admin_status = Column(String(20), default="unknown") # up, down, testing, unknown
    speed = Column(Integer)  # Mbps
    duplex = Column(String(20))  # full, half, auto
    mtu = Column(Integer)
    vlan_id = Column(Integer)
    metadata = Column(JSONB, default=dict)
    discovered_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    device = relationship("Device", back_populates="interfaces")

    __table_args__ = (
        Index("idx_interfaces_device_id", "device_id"),
        Index("idx_interfaces_name", "name"),
        Index("idx_interfaces_ip_address", "ip_address"),
        Index("idx_interfaces_mac_address", "mac_address"),
        Index("idx_interfaces_vlan_id", "vlan_id"),
        Index("idx_interfaces_status", "status"),
    )


class Discovery(Base):
    """Discovery run model"""
    __tablename__ = "discoveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    targets = Column(JSONB, nullable=False)  # Target networks/hosts
    scan_profile = Column(String(50), default="standard")  # standard, quick, deep
    status = Column(String(50), default="pending")  # pending, running, completed, failed, cancelled
    progress = Column(Integer, default=0)
    results = Column(JSONB, default=dict)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="discoveries")
    scans = relationship("Scan", back_populates="discovery", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_discoveries_organization_id", "organization_id"),
        Index("idx_discoveries_created_by", "created_by"),
        Index("idx_discoveries_status", "status"),
        Index("idx_discoveries_created_at", "created_at"),
    )


class Scan(Base):
    """Individual scan within a discovery"""
    __tablename__ = "scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    discovery_id = Column(UUID(as_uuid=True), ForeignKey("discoveries.id", ondelete="CASCADE"), nullable=False)
    scan_type = Column(String(50), nullable=False)  # nmap, snmp, ssh, api, cdp, lldp, flow
    target = Column(String(255), nullable=False)
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    results = Column(JSONB, default=dict)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    discovery = relationship("Discovery", back_populates="scans")

    __table_args__ = (
        Index("idx_scans_discovery_id", "discovery_id"),
        Index("idx_scans_scan_type", "scan_type"),
        Index("idx_scans_status", "status"),
        Index("idx_scans_target", "target"),
    )


class Configuration(Base):
    """
    Device configuration change-tracking log (cloud side).

    Privacy architecture:
      - ZERO config text ever reaches cloud — not raw, not sanitized, nothing.
      - The local agent parses configs with TextFSM → structured metadata → uploaded as JSONB.
      - This table records WHAT CHANGED between snapshots (structural diff, not text diff).

    What is stored:
      - config_hash: SHA-256 of raw config for change detection and deduplication
      - metadata_diff: JSONB summary of structural changes (added/removed interfaces,
        routing changes, security posture changes, etc.) — never ACL rules or credentials
      - config_type, captured_at: standard tracking fields

    What is NOT stored:
      - Any config text (not even sanitized)
      - ACL rules, credentials, NTP server IPs, syslog destinations, hostname values
    """
    __tablename__ = "configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    config_type = Column(String(50), default="running")  # running, startup, candidate
    # SHA-256 hash of the raw config — for change detection and deduplication only.
    config_hash = Column(String(64), nullable=False)
    # Structural diff between this snapshot and the previous one.
    # Contains only schema-level facts (interface added/removed, BGP neighbor count changed, etc.)
    metadata_diff = Column(JSONB, default=dict)
    captured_at = Column(DateTime(timezone=True), server_default=func.now())
    captured_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    device = relationship("Device", back_populates="configurations")

    __table_args__ = (
        Index("idx_configurations_device_id", "device_id"),
        Index("idx_configurations_config_hash", "config_hash"),
        Index("idx_configurations_captured_at", "captured_at"),
    )


class Credential(Base):
    """Stored credentials — encrypted at rest via Fernet (AES-128-CBC + HMAC-SHA256)"""
    __tablename__ = "credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    username = Column(String(255), nullable=False)
    encrypted_password = Column(EncryptedText, nullable=False)  # Transparently encrypted/decrypted
    credential_type = Column(String(50), nullable=False)  # password, ssh_key, api_token, snmp_community
    target_filter = Column(JSONB, default=dict)
    metadata = Column(JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="credentials")

    __table_args__ = (
        Index("idx_credentials_organization_id", "organization_id"),
        Index("idx_credentials_credential_type", "credential_type"),
    )


class IntegrationConfig(Base):
    """
    Per-organization external ticketing/notification system integration.

    Stores connection config and encrypted credentials for integrations such as
    ServiceNow, JIRA, Slack, Teams, PagerDuty, Opsgenie, GitHub, and Zendesk.

    Supported integration_type values:
      servicenow  — creates/updates Change Request records via Table API
      jira        — creates/transitions issues via REST API
      slack       — posts notifications to a channel via webhook or bot token
      teams       — posts to a Teams channel via incoming webhook
      pagerduty   — creates incidents or sends change events via Events API v2
      opsgenie    — creates alerts and attaches change evidence
      github      — creates issues or comments on PRs
      zendesk     — creates tickets

    config (JSONB) — integration-specific non-sensitive settings:
      ServiceNow: {"table": "change_request", "assignment_group": "Network CAB",
                   "category": "Network", "state_field": "state"}
      JIRA:       {"project_key": "NETOPS", "issue_type": "Change",
                   "priority_mapping": {"low": "Low", "high": "High", "critical": "Highest"}}
      Slack:      {"channel_id": "C12345678", "notify_on": ["pending_approval", "completed", "failed"]}
      Teams:      {"notify_on": ["pending_approval", "completed", "failed"]}
      PagerDuty:  {"routing_key": null,  # stored in encrypted_credentials
                   "escalation_policy": "P1234"}

    encrypted_credentials — Fernet-encrypted JSON string. Contents vary by type:
      ServiceNow: {"username": "...", "password": "..."}  or  {"oauth_token": "..."}
      JIRA:       {"api_token": "...", "email": "..."}
      Slack:      {"bot_token": "xoxb-..."}
      Teams:      {"webhook_url": "https://..."}
      PagerDuty:  {"routing_key": "..."}

    webhook_secret — Fernet-encrypted HMAC key for verifying inbound webhook payloads
      from the external system (e.g. ServiceNow calling us when a CAB approves).
    """
    __tablename__ = "integration_configs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)

    integration_type = Column(String(50), nullable=False)
    # servicenow, jira, slack, teams, pagerduty, opsgenie, github, zendesk, linear

    # Human-readable label for this integration (org may have multiple JIRA instances, etc.)
    name = Column(String(255), nullable=False)

    # Base URL for the external system's API (not needed for webhook-only integrations like Slack/Teams)
    base_url = Column(String(2048))
    # e.g. "https://yourorg.service-now.com"  or  "https://yourorg.atlassian.net"

    # Integration-specific non-sensitive configuration (see docstring for examples)
    config = Column(JSONB, default=dict)

    # Encrypted connection credentials — JSON string encrypted via Fernet
    # Contents vary by integration_type (see docstring)
    encrypted_credentials = Column(EncryptedText)

    # Encrypted HMAC secret for verifying inbound webhook signatures from the external system
    webhook_secret = Column(EncryptedText)

    is_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    organization = relationship("Organization", back_populates="integrations")

    __table_args__ = (
        Index("idx_integration_configs_organization_id", "organization_id"),
        Index("idx_integration_configs_integration_type", "integration_type"),
        Index("idx_integration_configs_is_enabled", "is_enabled"),
        # One named integration per org (prevents duplicate "Production ServiceNow" configs)
        UniqueConstraint("organization_id", "name", name="uq_integration_configs_org_name"),
    )


class ChangeRecord(Base):
    """
    Audit-grade change management record.

    This is the primary evidence artifact for compliance audits (PCI-DSS Req 6,
    SOX ITGC change management, ISO 27001 A.12.1.2). Every change to a network
    device goes through this lifecycle and is permanently retained.

    Lifecycle:
      draft → pending_approval → approved → scheduled → in_progress
             → completed | rolled_back | failed

    Evidence fields (what QSAs and auditors actually ask for):
      - change_number: human-readable reference (CHG-2026-0042)
      - requested_by / requested_at: who submitted and when
      - approved_by / approved_at / approval_notes: who approved, when, any conditions
      - affected_devices: which devices were in scope
      - pre_change_hash / post_change_hash: cryptographic proof of what changed
      - simulation_results: ContainerLab test evidence (if module enabled)
      - implementation_evidence: who applied it, when, maintenance window
      - verification_results: post-implementation validation results
      - rollback_performed: whether rollback was triggered and outcome
    """
    __tablename__ = "change_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)

    # Human-readable change number for referencing in tickets, emails, audit reports
    change_number = Column(String(50), unique=True, nullable=False)  # e.g. CHG-2026-0042

    # Status lifecycle
    status = Column(String(50), default="draft", nullable=False)
    # draft → pending_approval → approved → scheduled → in_progress → completed / rolled_back / failed

    # Change description — what is being changed and why
    change_type = Column(String(50))  # config_change, firmware_upgrade, acl_update, routing_change, etc.
    title = Column(String(500), nullable=False)
    description = Column(Text)
    risk_level = Column(String(20), default="medium")  # low, medium, high, critical
    compliance_justification = Column(Text)  # Why this change is needed for compliance/security

    # Affected scope
    affected_devices = Column(JSONB, default=list)  # List of device IDs in scope
    affected_compliance_scopes = Column(JSONB, default=list)  # e.g. ["PCI-CDE", "SOX-FINANCIAL"]

    # Request
    requested_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    scheduled_window_start = Column(DateTime(timezone=True))
    scheduled_window_end = Column(DateTime(timezone=True))

    # Human approval gate — mandatory, no exceptions
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    approved_at = Column(DateTime(timezone=True))
    approval_notes = Column(Text)

    # AI-generated proposed change (config sent down to local agent — never stored here)
    # We store the proposal description and hash, not the config text
    proposed_change_description = Column(Text)  # Human-readable description of proposed change
    proposed_change_hash = Column(String(64))   # SHA-256 of the proposed config change

    # Pre/post state hashes — cryptographic proof of what changed
    pre_change_hash = Column(String(64))   # config_hash before change applied
    post_change_hash = Column(String(64))  # config_hash after change applied

    # Test/simulation evidence (ContainerLab module — optional)
    simulation_performed = Column(Boolean, default=False)
    simulation_results = Column(JSONB, default=dict)  # pass/fail per test, convergence times, etc.
    simulation_passed = Column(Boolean)

    # Implementation record
    implemented_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    implemented_at = Column(DateTime(timezone=True))
    implementation_evidence = Column(JSONB, default=dict)  # CLI output snippets, API response codes

    # Post-implementation verification
    verification_results = Column(JSONB, default=dict)  # Automated checks run after change
    verification_passed = Column(Boolean)

    # Rollback
    rollback_plan = Column(Text)         # Rollback procedure description
    rollback_performed = Column(Boolean, default=False)
    rollback_at = Column(DateTime(timezone=True))
    rollback_reason = Column(Text)

    # External ticketing system reference — populated when the change record is synced
    # to ServiceNow, JIRA, etc. Null if no integration is configured.
    external_ticket_id = Column(String(255))    # ServiceNow sys_id, JIRA issue key, GitHub issue #
    external_ticket_url = Column(String(2048))  # Direct link to the external ticket
    ticket_system = Column(String(50))          # servicenow, jira, pagerduty, github, zendesk, linear

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_change_records_organization_id", "organization_id"),
        Index("idx_change_records_status", "status"),
        Index("idx_change_records_change_number", "change_number"),
        Index("idx_change_records_requested_at", "requested_at"),
        Index("idx_change_records_approved_by", "approved_by"),
        Index("idx_change_records_external_ticket_id", "external_ticket_id"),
        Index("idx_change_records_affected_compliance_scopes", "affected_compliance_scopes",
              postgresql_using="gin"),
    )


class ACLSnapshot(Base):
    """
    Zero-knowledge encrypted storage for firewall rules and ACL content.

    This is the Compliance Vault module — an optional add-on for customers who need
    to store and produce firewall rule evidence for audits (PCI-DSS, HIPAA, FedRAMP)
    without surrendering control of sensitive data to a third party.

    Zero-knowledge model:
      - The customer holds the encryption key. We never have it.
      - The local agent encrypts ACL content on-prem before sending.
      - We store an opaque encrypted blob — cryptographically unreadable to us.
      - Only the customer (with their key) can decrypt and present to auditors.
      - We can sign DPAs/BAAs stating we have NO TECHNICAL ABILITY to read this data.

    Encryption:
      - Algorithm: AES-256-GCM (authenticated encryption — integrity + confidentiality)
      - Key managed by customer: HashiCorp Vault transit, AWS KMS, Azure Key Vault,
        GCP CSEK, or self-managed (customer generates and holds key directly)
      - key_id: customer's key reference (Vault path, KMS ARN, etc.) — actual key never stored here

    Integrity verification:
      - content_hmac: HMAC-SHA256 of plaintext, computed on-prem with customer key
      - Customer can verify HMAC after decryption to confirm stored content is unmodified
      - We cannot compute or verify this HMAC (no key) — tamper-evidence is customer-controlled

    Audit workflow:
      1. Customer requests their ACL snapshot for a specific device/date
      2. We return encrypted_blob + content_hmac + capture metadata
      3. Customer decrypts with their key, verifies HMAC, presents plaintext to QSA
    """
    __tablename__ = "acl_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)

    # Content classification
    content_type = Column(String(50), nullable=False)
    # acl_rules, firewall_policy, nat_rules, security_policy, route_policy

    # Encrypted content — opaque to us, only customer can decrypt
    encrypted_blob = Column(Text, nullable=False)
    # HMAC-SHA256 of plaintext computed on-prem with customer key — for integrity verification
    content_hmac = Column(String(64), nullable=False)
    # Encrypted size in bytes (of plaintext, before encryption) — for storage planning
    plaintext_size_bytes = Column(Integer)

    # Key management metadata — reference only, actual key is NEVER stored here
    key_id = Column(String(500), nullable=False)
    # e.g. "vault://transit/acl-vault-key", "arn:aws:kms:us-east-1:123:key/abc", "self-managed:v1"
    key_provider = Column(String(50), nullable=False)
    # hashicorp_vault, aws_kms, azure_key_vault, gcp_csek, self_managed
    encryption_algorithm = Column(String(50), default="AES-256-GCM", nullable=False)

    # Collection metadata (plaintext — not sensitive)
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    captured_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    # Config hash links this ACL snapshot to the Configuration change record at the same point in time
    config_hash_at_capture = Column(String(64))
    compliance_scope = Column(JSONB, default=list)  # e.g. ["PCI-CDE", "PCI-BOUNDARY"]

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("idx_acl_snapshots_organization_id", "organization_id"),
        Index("idx_acl_snapshots_device_id", "device_id"),
        Index("idx_acl_snapshots_captured_at", "captured_at"),
        Index("idx_acl_snapshots_content_type", "content_type"),
        Index("idx_acl_snapshots_compliance_scope", "compliance_scope", postgresql_using="gin"),
    )


class Task(Base):
    """Celery task tracking"""
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True)
    task_name = Column(String(255), nullable=False)
    task_type = Column(String(50), nullable=False)
    status = Column(String(50), default="pending")  # pending, running, completed, failed, cancelled
    progress = Column(Integer, default=0)
    result = Column(JSONB, default=dict)
    error_message = Column(Text)
    parent_id = Column(UUID(as_uuid=True))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_organization_id", "organization_id"),
        Index("idx_tasks_parent_id", "parent_id"),
        Index("idx_tasks_created_at", "created_at"),
    )
