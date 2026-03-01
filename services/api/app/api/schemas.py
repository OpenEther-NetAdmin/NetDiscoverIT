"""
API Schemas
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


class User(BaseModel):
    """User schema"""
    id: str
    email: str
    organization_id: str
    role: str


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
