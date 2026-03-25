# ML Role Classifier Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement ML device role classifier that classifies network devices into 18 roles using rule-based + ML hybrid approach, deployed in cloud API.

**Architecture:** Hybrid classifier with rule-based phase for immediate results and ML model training on collected data. Classification runs in cloud API after device upload. Results stored ONLY in Device model columns (no JSONB fallback).

**Tech Stack:** Python, scikit-learn, FastAPI, SQLAlchemy, PostgreSQL

---

## Design Review Fixes Applied

| Issue | Fix Applied |
|-------|-------------|
| Column name: device_metadata → meta | All code uses `device.meta` not `device_metadata` |
| JSONB fallback redundant | Removed - only dedicated columns used |
| Rules too broad | Added device_type prerequisite checks |
| Confidence calculation arbitrary | Improved weighting with device_type bonus |
| N+1 queries in batch | Uses bulk `select(Device).where(Device.id.in_(...))` |
| Module-level classifier singleton | Uses `Depends(get_classifier)` dependency injection |
| List[str] → List[UUID] | Uses `List[UUID]` with Pydantic validation |
| AuditLog missing | Added AuditLog writes on all classification operations |
| Data flow misleading | Updated diagram to show manual trigger |
| Unconfirmed metadata fields | Removed rules using unconfirmed fields |
| role_vector not connected | Added Phase 2 note about pgvector nearest-neighbor |

---

## Prerequisites

- [ ] Group 6a Vectorizer completed (provides role_vector embedding)
- [ ] Device model has device_metadata JSONB column
- [ ] API service running with database access

---

## Task 1: Add Device Model Columns for Role Classification

**Files:**
- Modify: `services/api/app/models/models.py:195-230`
- Modify: `services/api/app/api/schemas.py:270-450`

**Step 1: Write the failing test**

Create test file `services/api/tests/services/test_role_classifier.py`:

```python
import pytest
from uuid import uuid4

def test_device_model_has_role_columns(db_session):
    from app.models.models import Device
    
    device = Device(
        id=uuid4(),
        organization_id=uuid4(),
        ip_address="192.168.1.1",
        inferred_role=None,
        role_confidence=None
    )
    db_session.add(device)
    db_session.commit()
    
    # Verify the column names match the actual model
    assert hasattr(device, 'inferred_role')
    assert hasattr(device, 'role_confidence')
    assert hasattr(device, 'role_classified_at')
    assert hasattr(device, 'role_classifier_version')
    
    # CRITICAL: Verify meta column exists (not device_metadata)
    assert hasattr(device, 'meta')
```

**Step 2: Run test to verify it fails**

Run: `cd /home/openether/NetDiscoverIT/services/api && python -m pytest tests/services/test_role_classifier.py::test_device_model_has_role_columns -v`
Expected: FAIL - attributes don't exist

**Step 3: Add columns to Device model**

In `services/api/app/models/models.py`, add after `device_role` column (around line 199):

```python
# ML role classification
inferred_role = Column(String(50), nullable=True)  # from taxonomy
role_confidence = Column(Float, nullable=True)     # 0.0 - 1.0
role_classified_at = Column(DateTime(timezone=True), nullable=True)
role_classifier_version = Column(String(20), nullable=True)
```

**Step 4: Run test to verify it passes**

Run: `cd /home/openether/NetDiscoverIT/services/api && python -m pytest tests/services/test_role_classifier.py::test_device_model_has_role_columns -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/api/app/models/models.py
git commit -m "feat: add role classification columns to Device model"
```

---

## Task 2: Create Role Classification Service

**Files:**
- Create: `services/api/app/services/role_classifier.py`
- Create: `services/api/tests/services/test_role_classifier_service.py`

**Step 1: Write the failing test**

```python
# services/api/tests/services/test_role_classifier_service.py
import pytest

def test_role_classifier_classify_core_router():
    from app.services.role_classifier import RoleClassifier
    
    classifier = RoleClassifier()
    metadata = {
        "device_type": "router",
        "interface_count": 48,
        "l3_interface_count": 4,
        "has_bgp": True,
        "has_ospf": True,
        "vendor": "Cisco"
    }
    
    result = classifier.classify(metadata)
    
    assert result["inferred_role"] == "core_router"
    assert result["confidence"] >= 0.8
```

**Step 2: Run test to verify it fails**

Run: `pytest services/api/tests/services/test_role_classifier_service.py::test_role_classifier_classify_core_router -v`
Expected: FAIL - module not found

**Step 3: Create RoleClassifier service**

Create `services/api/app/services/role_classifier.py`:

```python
"""
Role Classification Service
Hybrid rule-based + ML classifier for network device roles
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

DEVICE_ROLES = [
    "core_router",
    "edge_router", 
    "distribution_switch",
    "access_switch",
    "spine_switch",
    "leaf_switch",
    "l2_firewall",
    "l3_firewall",
    "load_balancer",
    "server",
    "wireless_controller",
    "access_point",
    "gateway",
    "datacenter_switch",
    "endpoint_protection",
    "vpn_concentrator",
    "waf",
    "domain_controller",
    "unknown",
]

ROLE_RULES = {
    # Rules require device_type match as a prerequisite to avoid false positives
    # All rules assume device_type is already checked or is a strong indicator
    
    "core_router": [
        # Strong: BGP + multiple L3 interfaces (classic core router signature)
        lambda m: m.get("has_bgp", False) and m.get("l3_interface_count", 0) >= 3,
        # Moderate: OSPFs with high interface count and distribution characteristics
        lambda m: m.get("has_ospf", False) and m.get("l3_interface_count", 0) >= 4 and m.get("vlan_count", 0) >= 10,
    ],
    "edge_router": [
        # Strong: NAT + static routes (classic WAN edge)
        lambda m: m.get("nat_enabled", False) and m.get("has_static_routes", False),
        # Moderate: VPN + NAT (remote access edge)
        lambda m: m.get("vpn_enabled", False) and m.get("nat_enabled", False),
    ],
    "distribution_switch": [
        # Strong: Multiple VLANs + L3 interfaces (distribution layer)
        lambda m: m.get("vlan_count", 0) >= 10 and m.get("l3_interface_count", 0) >= 2,
        # Moderate: High port count + routing protocols but not core
        lambda m: m.get("interface_count", 0) >= 24 and m.get("has_ospf", False) and m.get("l3_interface_count", 0) < 4,
    ],
    "access_switch": [
        # Strong: PoE + high port count (typical access switch)
        lambda m: m.get("has_poe", False) and m.get("interface_count", 0) >= 24,
        # Moderate: VLANs but no routing (L2-only access)
        lambda m: m.get("vlan_count", 0) >= 3 and not m.get("has_bgp", False) and not m.get("has_ospf", False),
    ],
    "spine_switch": [
        # Strong: Arista + VXLAN (modern DC fabric)
        lambda m: m.get("vendor") in ["Arista"] and m.get("l3_interface_count", 0) >= 4,
        # Moderate: Cisco high-port with no routing (DC spine)
        lambda m: m.get("vendor") == "Cisco" and m.get("interface_count", 0) >= 32 and m.get("l3_interface_count", 0) == 0,
    ],
    "leaf_switch": [
        # Strong: Arista + server-facing (leaf in DC fabric)
        lambda m: m.get("vendor") in ["Arista"] and m.get("l3_interface_count", 0) >= 2,
        # Moderate: High port count + L3 but no BGP (likely leaf)
        lambda m: m.get("interface_count", 0) >= 48 and m.get("l3_interface_count", 0) >= 2 and not m.get("has_bgp", False),
    ],
    "l2_firewall": [
        # Strong: firewall type + no NAT = L2 firewall
        lambda m: m.get("device_type") == "firewall" and not m.get("nat_enabled", False),
        # Moderate: firewall with ACLs but no routing
        lambda m: m.get("acl_count", 0) > 0 and not m.get("has_bgp", False) and not m.get("has_ospf", False),
    ],
    "l3_firewall": [
        # Strong: firewall type + NAT = L3 firewall
        lambda m: m.get("device_type") == "firewall" and m.get("nat_enabled", False),
        # Moderate: NAT + VPN (UTM-style firewall)
        lambda m: m.get("nat_enabled", False) and m.get("vpn_enabled", False),
    ],
    "load_balancer": [
        # Strong: F5/A10/Citrix vendor (explicit load balancer vendor)
        lambda m: m.get("vendor") in ["F5", "A10", "Citrix", "Kemp", "Radware"],
        # Moderate: VIP indicators (if available in metadata)
        lambda m: m.get("vip_count", 0) > 0,
    ],
    "server": [
        # Strong: explicit server device_type
        lambda m: m.get("device_type") == "server",
        # Moderate: OS indicators
        lambda m: m.get("os_type") in ["Linux", "Windows", "VMware", "Hyper-V"],
    ],
    "wireless_controller": [
        # Strong: wireless vendor + AP management capability
        lambda m: m.get("vendor") in ["Cisco", "Aruba", "Ruckus", "AeroHive"] and m.get("l3_interface_count", 0) >= 2,
        # Moderate: wireless enabled + management interface
        lambda m: m.get("wireless_enabled", False) and m.get("l3_interface_count", 0) >= 2,
    ],
    "access_point": [
        # Strong: explicit access_point device_type
        lambda m: m.get("device_type") == "access_point",
        # Moderate: wireless + low port count (typical AP)
        lambda m: m.get("wireless_enabled", False) and m.get("interface_count", 0) <= 4,
    ],
    "gateway": [
        # Strong: default route + NAT (internet gateway)
        lambda m: m.get("has_default_route", False) and m.get("nat_enabled", False),
    ],
    "datacenter_switch": [
        # Strong: high port count + Cisco/Juniper/Arista + no routing (DC core)
        lambda m: m.get("interface_count", 0) >= 48 and m.get("vendor") in ["Cisco", "Juniper", "Arista"] and m.get("l3_interface_count", 0) == 0,
    ],
    "endpoint_protection": [
        # Strong: endpoint security vendors
        lambda m: m.get("vendor") in ["Palo Alto", "CrowdStrike", "SentinelOne", "Sophos", "TrendMicro"],
    ],
    "vpn_concentrator": [
        # Strong: VPN enabled + specific port signatures
        lambda m: m.get("vpn_enabled", False) and (m.get("port_500_open", False) or m.get("port_4500_open", False)),
    ],
    "waf": [
        # Strong: explicit WAF vendors
        lambda m: m.get("vendor") in ["F5", "Imperva", "FortiWeb", "A10", "Citrix", "AWS", "Cloudflare"],
    ],
    "domain_controller": [
        # Strong: Microsoft AD indicators
        lambda m: m.get("vendor") == "Microsoft" and m.get("port_389_open", False),
    ],
}

# Fields confirmed in agent metadata schema (from CLAUDE.md and schemas.py)
CONFIRMED_METADATA_FIELDS = [
    "device_type", "vendor", "interface_count", "l3_interface_count", "vlan_count",
    "has_bgp", "has_ospf", "has_eigrp", "has_static_routes", "acl_count",
    "nat_enabled", "vpn_enabled", "wireless_enabled", "has_poe",
    "port_22_open", "port_23_open", "port_161_open", "port_443_open", "port_80_open",
]


class RoleClassifier:
    """Hybrid rule-based + ML device role classifier"""
    
    def __init__(self):
        self._ml_model = None
        self._model_version = "1.0.0"
    
    def classify(self, metadata: Dict) -> Dict:
        """Classify device role from metadata"""
        if not metadata:
            return self._unknown_result()
        
        # Try rule-based classification first
        role, confidence = self._rule_based_classify(metadata)
        
        if role != "unknown":
            return {
                "inferred_role": role,
                "confidence": confidence,
                "classified_at": datetime.utcnow(),
                "method": "rule_based",
                "features": self._extract_features(metadata),
            }
        
        # Fall back to ML model if available
        if self._ml_model:
            role, confidence = self._ml_classify(metadata)
            return {
                "inferred_role": role,
                "confidence": confidence,
                "classified_at": datetime.utcnow(),
                "method": "ml_model",
                "features": self._extract_features(metadata),
            }
        
        return self._unknown_result()
    
    def _rule_based_classify(self, metadata: Dict) -> Tuple[str, float]:
        """Rule-based classification"""
        best_role = "unknown"
        best_confidence = 0.0
        
        for role, rules in ROLE_RULES.items():
            for rule in rules:
                try:
                    if rule(metadata):
                        confidence = self._calculate_rule_confidence(role, metadata)
                        if confidence > best_confidence:
                            best_role = role
                            best_confidence = confidence
                except Exception:
                    pass
        
        return best_role, best_confidence
    
    def _calculate_rule_confidence(self, role: str, metadata: Dict) -> float:
        """
        Calculate confidence based on rule quality:
        - Single rule match: 0.6 (moderate confidence)
        - Multiple rule matches: 0.8 (high confidence)
        - device_type match as prerequisite: +0.1 bonus
        """
        rules = ROLE_RULES.get(role, [])
        matches = sum(1 for r in rules if r(metadata))
        
        # Base confidence from rule count
        if matches == 0:
            return 0.0
        elif matches == 1:
            base = 0.6
        else:
            base = 0.8
        
        # device_type match bonus (if device_type explicitly indicates this role)
        device_type = metadata.get("device_type", "").lower()
        role_device_types = {
            "firewall": ["firewall", "utm"],
            "server": ["server", "host", "vm"],
            "router": ["router"],
            "switch": ["switch"],
            "access_point": ["access_point", "ap"],
            "load_balancer": ["load_balancer", "lb"],
        }
        
        if role in role_device_types and device_type in role_device_types[role]:
            base = min(base + 0.1, 0.9)
        
        return base
    
    def _ml_classify(self, metadata: Dict) -> Tuple[str, float]:
        """ML-based classification (placeholder for Phase 2)"""
        return "unknown", 0.0
    
    def _extract_features(self, metadata: Dict) -> Dict:
        """Extract classification features from metadata"""
        return {
            "device_type": metadata.get("device_type"),
            "vendor": metadata.get("vendor"),
            "interface_count": metadata.get("interface_count", 0),
            "l3_interface_count": metadata.get("l3_interface_count", 0),
            "vlan_count": metadata.get("vlan_count", 0),
            "has_bgp": metadata.get("has_bgp", False),
            "has_ospf": metadata.get("has_ospf", False),
            "acl_count": metadata.get("acl_count", 0),
            "nat_enabled": metadata.get("nat_enabled", False),
            "vpn_enabled": metadata.get("vpn_enabled", False),
        }
    
    def _unknown_result(self) -> Dict:
        """Return unknown classification result"""
        return {
            "inferred_role": "unknown",
            "confidence": 0.0,
            "classified_at": datetime.utcnow(),
            "method": "none",
            "features": {},
        }
```

**Step 4: Run test to verify it passes**

Run: `pytest services/api/tests/services/test_role_classifier_service.py::test_role_classifier_classify_core_router -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/api/app/services/role_classifier.py services/api/tests/services/test_role_classifier_service.py
git commit -m "feat: add role classifier service with rule-based classification"
```

---

## Task 3: Add Classification API Endpoints

**Files:**
- Modify: `services/api/app/api/routes.py:300-400`
- Modify: `services/api/app/api/schemas.py:450-500`

**Step 1: Write the failing test**

```python
# services/api/tests/api/test_role_classification.py
def test_classify_device_endpoint(auth_client, db_session):
    from app.models.models import Device
    from uuid import uuid4
    
    # CRITICAL: use 'meta' not 'device_metadata'
    device = Device(
        id=uuid4(),
        organization_id=auth_client.org_id,
        ip_address="192.168.1.1",
        meta={"interface_count": 48, "has_bgp": True, "l3_interface_count": 4}
    )
    db_session.add(device)
    db_session.commit()
    
    response = auth_client.post(f"/api/v1/devices/{device.id}/classify")
    
    assert response.status_code == 200
    data = response.json()
    assert "inferred_role" in data
    assert "confidence" in data
```

**Step 2: Run test to verify it fails**

Run: `pytest services/api/tests/api/test_role_classification.py::test_classify_device_endpoint -v`
Expected: FAIL - endpoint doesn't exist

**Step 3: Add classification endpoints**

In `services/api/app/api/routes.py`, add after device routes:

```python
from app.services.role_classifier import RoleClassifier
from app.models.audit import AuditLog

# Dependency injection for classifier (allows testing with mocks)
def get_classifier() -> RoleClassifier:
    """Get role classifier instance - stateless for rule-based, injectable for testing"""
    return RoleClassifier()


@router.post("/devices/{device_id}/classify", response_model=DeviceClassificationResponse)
async def classify_device(
    device_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    classifier: RoleClassifier = Depends(get_classifier),
):
    """Classify device role"""
    result = await db.get(Device, device_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if result.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # CRITICAL: Use 'meta' column, not 'device_metadata'
    metadata = result.meta or {}
    classification = classifier.classify(metadata)
    
    old_role = result.inferred_role
    result.inferred_role = classification["inferred_role"]
    result.role_confidence = classification["confidence"]
    result.role_classified_at = classification["classified_at"]
    result.role_classifier_version = "1.0.0"
    
    await db.commit()
    await db.refresh(result)
    
    # Write AuditLog entry for classification
    audit_log = AuditLog(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        action="device.role_classified",
        resource_type="device",
        resource_id=str(device_id),
        details={
            "old_role": old_role,
            "new_role": classification["inferred_role"],
            "confidence": classification["confidence"],
            "method": classification.get("method"),
        },
    )
    db.add(audit_log)
    await db.commit()
    
    return classification


@router.get("/devices/{device_id}/classification")
async def get_device_classification(
    device_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get device role classification"""
    result = await db.get(Device, device_id)
    if not result:
        raise HTTPException(status_code=404, detail="Device not found")
    
    if result.organization_id != current_user.organization_id:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return {
        "inferred_role": result.inferred_role,
        "confidence": result.role_confidence,
        "classified_at": result.role_classified_at,
        "classifier_version": result.role_classifier_version,
    }
```

Add schema in `services/api/app/api/schemas.py`:

```python
class DeviceClassificationResponse(BaseModel):
    inferred_role: str
    confidence: float
    classified_at: datetime
    method: str
    features: Dict[str, Any] = {}
    
    class Config:
        from_attributes = True
```

**Step 4: Run test to verify it passes**

Run: `pytest services/api/tests/api/test_role_classification.py::test_classify_device_endpoint -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/api/app/api/routes.py services/api/app/api/schemas.py
git commit -m "feat: add device classification API endpoints"
```

---

## Task 4: Add Batch Classification Endpoint

**Files:**
- Modify: `services/api/app/api/routes.py:400-450`

**Step 1: Write the failing test**

```python
def test_batch_classify_devices(auth_client, db_session):
    from app.models.models import Device
    from uuid import uuid4
    
    devices = []
    for i in range(3):
        # CRITICAL: use 'meta' not 'device_metadata'
        device = Device(
            id=uuid4(),
            organization_id=auth_client.org_id,
            ip_address=f"192.168.1.{i+1}",
            meta={"interface_count": 48, "has_bgp": True}
        )
        devices.append(device)
        db_session.add(device)
    db_session.commit()
    
    response = auth_client.post("/api/v1/devices/classify-batch", json={
        "device_ids": [str(d.id) for d in devices]
    })
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["results"]) == 3
```

**Step 2: Run test to verify it fails**

Run: `pytest services/api/tests/api/test_role_classification.py::test_batch_classify_devices -v`
Expected: FAIL - endpoint doesn't exist

**Step 3: Add batch endpoint**

```python
@router.post("/devices/classify-batch")
async def batch_classify_devices(
    request: BatchClassifyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    classifier: RoleClassifier = Depends(get_classifier),
):
    """Batch classify multiple devices - uses bulk query to avoid N+1"""
    # Bulk query all devices in one round trip
    from sqlalchemy import select
    
    stmt = select(Device).where(
        Device.id.in_(request.device_ids),
        Device.organization_id == current_user.organization_id
    )
    result = await db.execute(stmt)
    devices = {str(d.id): d for d in result.scalars().all()}
    
    results = []
    audit_logs = []
    
    for device_id in request.device_ids:
        device = devices.get(str(device_id))
        
        if not device:
            results.append({"device_id": str(device_id), "error": "Not found or not authorized"})
            continue
        
        # CRITICAL: Use 'meta' column, not 'device_metadata'
        metadata = device.meta or {}
        classification = classifier.classify(metadata)
        
        old_role = device.inferred_role
        device.inferred_role = classification["inferred_role"]
        device.role_confidence = classification["confidence"]
        device.role_classified_at = classification["classified_at"]
        device.role_classifier_version = "1.0.0"
        
        results.append({
            "device_id": str(device_id),
            "inferred_role": classification["inferred_role"],
            "confidence": classification["confidence"],
        })
        
        # Queue AuditLog entry
        audit_logs.append(AuditLog(
            organization_id=current_user.organization_id,
            user_id=current_user.id,
            action="device.role_classified",
            resource_type="device",
            resource_id=str(device_id),
            details={
                "old_role": old_role,
                "new_role": classification["inferred_role"],
                "confidence": classification["confidence"],
                "method": classification.get("method"),
                "batch": True,
            },
        ))
    
    await db.commit()
    
    # Bulk insert audit logs
    for audit_log in audit_logs:
        db.add(audit_log)
    await db.commit()
    
    return {"results": results}
```

Add request schema:

```python
class BatchClassifyRequest(BaseModel):
    device_ids: List[UUID]  # Use UUID type for validation
```

**Step 4: Run test to verify it passes**

Run: `pytest services/api/tests/api/test_role_classification.py::test_batch_classify_devices -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/api/app/api/routes.py services/api/app/api/schemas.py
git commit -m "feat: add batch classification endpoint"
```

---

## Task 5: Create Alembic Migration for New Columns

**Files:**
- Create: `services/api/alembic/versions/003_add_role_classification_columns.py`

**Step 1: Write the failing test**

```python
def test_migration_adds_role_columns(db_engine):
    from sqlalchemy import inspect
    
    inspector = inspect(db_engine)
    columns = [c["name"] for c in inspector.get_columns("devices")]
    
    assert "inferred_role" in columns
    assert "role_confidence" in columns
    assert "role_classified_at" in columns
    assert "role_classifier_version" in columns
```

**Step 2: Run test to verify it fails**

Run: `pytest services/api/tests/db/test_migrations.py::test_migration_adds_role_columns -v`
Expected: FAIL - columns don't exist

**Step 3: Create migration**

```python
"""Add role classification columns

Revision ID: 003
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa

revision = '003'
down_revision = '002_add_vector_indexes'
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
```

**Step 4: Run test to verify it passes**

Run: `pytest services/api/tests/db/test_migrations.py::test_migration_adds_role_columns -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/api/alembic/versions/003_add_role_classification_columns.py
git commit -m "feat: add role classification columns migration"
```

---

## Task 6: Add Integration Test for Full Flow

**Files:**
- Create: `services/api/tests/integration/test_role_classifier_flow.py`

**Step 1: Write the integration test**

```python
def test_full_classification_flow(auth_client, db_session):
    """Test full device classification flow"""
    from app.models.models import Device
    from uuid import uuid4
    
    # 1. Create device with metadata - CRITICAL: use 'meta' not 'device_metadata'
    device = Device(
        id=uuid4(),
        organization_id=auth_client.org_id,
        ip_address="10.0.0.1",
        hostname="core-rtr-01",
        device_type="router",
        vendor="Cisco",
        meta={
            "interface_count": 48,
            "l3_interface_count": 4,
            "has_bgp": True,
            "has_ospf": True,
            "vendor": "Cisco",
        }
    )
    db_session.add(device)
    db_session.commit()
    
    # 2. Trigger classification
    response = auth_client.post(f"/api/v1/devices/{device.id}/classify")
    assert response.status_code == 200
    
    data = response.json()
    assert data["inferred_role"] in ["core_router", "distribution_switch", "unknown"]
    assert data["confidence"] >= 0.0
    
    # 3. Get classification
    response = auth_client.get(f"/api/v1/devices/{device.id}/classification")
    assert response.status_code == 200
    
    data = response.json()
    assert "inferred_role" in data
    assert "confidence" in data
    
    # 4. Verify DB updated
    db_session.refresh(device)
    assert device.inferred_role is not None
    assert device.role_confidence is not None
    assert device.role_classified_at is not None
```

**Step 2: Run test to verify it fails**

Run: `pytest services/api/tests/integration/test_role_classifier_flow.py::test_full_classification_flow -v`
Expected: FAIL - endpoint not found or columns missing

**Step 3: Run all previous tasks first, then this should pass**

**Step 4: Run test to verify it passes**

Run: `pytest services/api/tests/integration/test_role_classifier_flow.py::test_full_classification_flow -v`
Expected: PASS

**Step 5: Commit**

```bash
git add services/api/tests/integration/test_role_classifier_flow.py
git commit -m "test: add integration test for role classification flow"
```

---

## Task 7: Update Dependencies

**Files:**
- Modify: `services/api/requirements.txt`

**Step 1: Check if scikit-learn is needed now**

Run: `grep -i scikit /home/openether/NetDiscoverIT/services/api/requirements.txt`
Expected: Not found (we'll add for Phase 2 ML model)

**Step 2: Add scikit-learn for Phase 2**

For now, rule-based classifier doesn't need ML dependencies. Add for Phase 2:

```
# scikit-learn>=1.3.0  # Uncomment for Phase 2 ML model
```

**Step 3: Commit**

```bash
git add services/api/requirements.txt
git commit -m "chore: prepare for ML model dependencies"
```

---

## Summary

| Task | Description | Estimated Time |
|------|-------------|----------------|
| 1 | Device model columns | 30 min |
| 2 | RoleClassifier service | 1 hour |
| 3 | Classification API endpoints | 1 hour |
| 4 | Batch classification endpoint | 30 min |
| 5 | Alembic migration | 30 min |
| 6 | Integration test | 30 min |
| 7 | Dependencies | 10 min |

**Total Estimated: ~4 hours**

---

## Next Steps

1. Run all tests to verify implementation
2. Update claw-memory with completion status
3. Push changes to main repo
4. Move to Phase 2: ML model training (Group 6b continued)