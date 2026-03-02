"""
Database Models - PostgreSQL
Based on net-discit database-schemas.md
"""

from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Column, String, Text, Integer, Boolean, DateTime, ForeignKey,
    UniqueConstraint, Index, func, inet, macaddr
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


class Organization(Base):
    """Organization model"""
    __tablename__ = "organizations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    settings = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    users = relationship("User", back_populates="organization", cascade="all, delete-orphan")
    devices = relationship("Device", back_populates="organization", cascade="all, delete-orphan")
    discoveries = relationship("Discovery", back_populates="organization", cascade="all, delete-orphan")
    credentials = relationship("Credential", back_populates="organization", cascade="all, delete-orphan")


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
    metadata = Column(JSONB, default={})
    discovered_at = Column(DateTime(timezone=True), server_default=func.now())
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    
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
        UniqueConstraint("organization_id", "ip_address", name="idx_devices_org_ip", postgresql_where=is_active),
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
    status = Column(String(20), default="unknown")  # up, down, testing, unknown
    admin_status = Column(String(20), default="unknown")  # up, down, testing, unknown
    speed = Column(Integer)  # Mbps
    duplex = Column(String(20))  # full, half, auto
    mtu = Column(Integer)
    vlan_id = Column(Integer)
    metadata = Column(JSONB, default={})
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
    results = Column(JSONB, default={})
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
    scan_type = Column(String(50), nullable=False)  # nmap, snmp, ssh, api
    target = Column(String(255), nullable=False)
    status = Column(String(50), default="pending")  # pending, running, completed, failed
    results = Column(JSONB, default={})
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    discovery = relationship("Discovery", back_populates="scans")
    
    __table_args__ = (
        Index("idx_scans_discovery_id", "discovery_id"),
        Index("idx_scans_scan_type", "scan_type"),
        Index("idx_scans_status", "status"),
        Index("idx_scans_target", "target"),
    )


class Configuration(Base):
    """Device configuration snapshot"""
    __tablename__ = "configurations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    config_type = Column(String(50), default="running")  # running, startup, candidate
    raw_config = Column(Text)
    config_hash = Column(String(64), nullable=False)
    storage_path = Column(Text)
    file_size = Column(Integer)
    captured_at = Column(DateTime(timezone=True), server_default=func.now())
    captured_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    
    # Relationships
    device = relationship("Device", back_populates="configurations")
    
    __table_args__ = (
        Index("idx_configurations_device_id", "device_id"),
        Index("idx_configurations_config_hash", "config_hash"),
        Index("idx_configurations_captured_at", "captured_at"),
    )


class Credential(Base):
    """Stored credentials (encrypted)"""
    __tablename__ = "credentials"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    username = Column(String(255), nullable=False)
    encrypted_password = Column(Text, nullable=False)  # Should be encrypted
    credential_type = Column(String(50), nullable=False)  # password, ssh_key, api_token, snmp_community
    target_filter = Column(JSONB, default={})
    metadata = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    organization = relationship("Organization", back_populates="credentials")
    
    __table_args__ = (
        Index("idx_credentials_organization_id", "organization_id"),
        Index("idx_credentials_credential_type", "credential_type"),
    )


class Task(Base):
    """Celery task tracking"""
    __tablename__ = "tasks"
    
    id = Column(UUID(as_uuid=True), primary_key=True)
    task_name = Column(String(255), nullable=False)
    task_type = Column(String(50), nullable=False)
    status = Column(String(50), default="pending")  # pending, running, completed, failed, cancelled
    progress = Column(Integer, default=0)
    result = Column(JSONB, default={})
    error_message = Column(Text)
    parent_id = Column(UUID(as_uuid=True))
    organization_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    
    __table_args__ = (
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_organization_id", "organization_id"),
        Index("idx_tasks_parent_id", "parent_id"),
        Index("idx_tasks_created_at", "created_at"),
    )
