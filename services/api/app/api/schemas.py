"""
API Schemas
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum


class User(BaseModel):
    """User schema for authentication/internal use"""

    id: str
    email: str
    organization_id: str
    role: str
    full_name: str | None = None
    is_active: bool = True


class UserLogin(BaseModel):
    """User login request"""

    email: EmailStr
    password: str


class UserCreate(BaseModel):
    """User creation request"""

    email: EmailStr
    password: str
    full_name: str | None = None
    role: str = "viewer"


class UserUpdate(BaseModel):
    """User update request"""

    email: EmailStr | None = None
    full_name: str | None = None
    role: str | None = None
    password: str | None = None
    is_active: bool | None = None


class UserResponse(BaseModel):
    """User response (excludes sensitive fields)"""

    id: str
    email: str
    organization_id: str
    full_name: str | None = None
    role: str
    is_active: bool
    last_login: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    """JWT token response"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class DeviceBase(BaseModel):
    """Base device schema"""

    hostname: str
    management_ip: str
    vendor: Optional[str] = None
    device_type: Optional[str] = None
    role: Optional[str] = None


class DeviceCreate(DeviceBase):
    """Device creation schema"""

    pass


class DeviceUpdate(BaseModel):
    """Device update schema"""

    hostname: str | None = None
    management_ip: str | None = None
    vendor: str | None = None
    device_type: str | None = None
    role: str | None = None


class Device(DeviceBase):
    """Device response schema"""

    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DiscoveryStatus(str, Enum):
    """Discovery status"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DiscoveryBase(BaseModel):
    """Base discovery schema"""

    name: str
    discovery_type: str = "full"


class DiscoveryCreate(DiscoveryBase):
    """Discovery creation schema"""

    pass


class Discovery(DiscoveryBase):
    """Discovery response schema"""

    id: str
    organization_id: str
    status: DiscoveryStatus
    device_count: int = 0
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class DeviceMetadata(BaseModel):
    """Device metadata from agent"""

    device_id: str
    hostname: str
    management_ip: str
    vendor: str
    device_type: str
    role: str
    metadata: dict = {}


class CredentialType(str, Enum):
    """Credential types"""

    PASSWORD = "password"
    SSH_KEY = "ssh_key"
    API_TOKEN = "api_token"
    SNMP_COMMUNITY = "snmp_community"


class CredentialBase(BaseModel):
    """Base credential schema"""

    name: str
    username: str
    credential_type: CredentialType
    target_filter: dict = {}
    metadata: dict = {}


class CredentialCreate(CredentialBase):
    """Credential creation request (includes password)"""

    password: str  # Will be encrypted


class CredentialResponse(CredentialBase):
    """Credential response (excludes password)"""

    id: str
    organization_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class IntegrationType(str, Enum):
    """Integration types"""

    SERVICENOW = "servicenow"
    JIRA = "jira"
    SLACK = "slack"
    TEAMS = "teams"
    PAGERDUTY = "pagerduty"
    OPSGENIE = "opsgenie"
    GITHUB = "github"
    ZENDESK = "zendesk"


class IntegrationConfigBase(BaseModel):
    """Base integration config schema"""

    integration_type: IntegrationType
    name: str
    base_url: str | None = None
    config: dict = {}


class IntegrationConfigCreate(IntegrationConfigBase):
    """Integration config creation (includes credentials)"""

    credentials: dict  # Will be encrypted
    webhook_secret: str | None = None


class IntegrationConfigResponse(IntegrationConfigBase):
    """Integration config response (excludes secrets)"""

    id: str
    organization_id: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VectorData(BaseModel):
    """Vector data for a device"""

    device_role: List[float]
    topology: List[float]
    security: List[float]


class VectorDevice(BaseModel):
    """Device with vectors"""

    device_id: str
    metadata: DeviceMetadata
    vectors: VectorData


class VectorBatch(BaseModel):
    """Batch of vectors from agent"""

    batch_id: str
    customer_id: str
    timestamp: datetime
    devices: List[VectorDevice]
    recommendations_requested: bool = False


class PathHop(BaseModel):
    """Single hop in path"""

    hop: int
    device: dict
    interface: dict
    egress: dict
    acl_check: Optional[dict] = None


class PathTraceRequest(BaseModel):
    """Path trace request"""

    source_ip: str = Field(..., description="Source IP address")
    destination_ip: str = Field(..., description="Destination IP address")
    protocol: str = "tcp"
    port: Optional[int] = None


class PathResult(BaseModel):
    """Path trace result"""

    path_found: bool
    hops: List[PathHop] = []
    summary: dict = {}
    analysis: dict = {}
    issues: List[dict] = []


class SiteBase(BaseModel):
    """Base site schema"""

    name: str
    description: str | None = None
    site_type: str = "on_premises"
    location_address: str | None = None
    timezone: str = "UTC"


class SiteCreate(SiteBase):
    """Site creation schema"""

    pass


class SiteUpdate(BaseModel):
    """Site update schema"""

    name: str | None = None
    description: str | None = None
    site_type: str | None = None
    location_address: str | None = None
    timezone: str | None = None
    is_active: bool | None = None


class SiteResponse(SiteBase):
    """Site response schema"""

    id: str
    organization_id: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentBase(BaseModel):
    """Base agent schema"""
    name: str


class AgentResponse(BaseModel):
    """Agent response schema"""
    id: str
    organization_id: str
    site_id: str | None = None
    name: str
    agent_version: str | None = None
    last_seen: datetime | None = None
    is_active: bool
    capabilities: dict = {}
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AgentRotateKeyResponse(BaseModel):
    """Response when rotating agent key"""
    agent_id: str
    new_api_key: str
    message: str


class HeartbeatRequest(BaseModel):
    """Agent heartbeat request"""
    agent_version: str | None = None
    capabilities: dict = {}


class HeartbeatResponse(BaseModel):
    """Agent heartbeat response"""
    status: str
    agent_id: str
    last_seen: datetime
