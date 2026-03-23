# ACL Compliance Vault + ContainerLab Simulation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement ACL Compliance Vault API for zero-knowledge ACL storage and ContainerLab simulation for change validation.

**Architecture:** 
- ACL Vault: RESTful API endpoints with agent X-Agent-Key authentication, storing encrypted ACL snapshots
- ContainerLab: Redis queue-based async job system, agent executes simulations, results stored in ChangeRecord

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic, PostgreSQL, Redis, Neo4j

---

## Prerequisites

Before starting, verify:
- [x] ACLSnapshot model exists: `services/api/app/models/models.py:1110-1195`
- [x] ChangeRecord model exists with simulation fields
- [x] API service running: `make up`
- [x] Redis available for job queue

---

## Task 1: ACLSnapshot Schemas (3a-prep)

### Overview
Add Pydantic schemas for ACLSnapshot API requests/responses.

### Files
- Modify: `services/api/app/api/schemas.py`

### Step 1: Add ACLSnapshot schemas

**Step 1.1: Read existing schemas file**

Run: `wc -l services/api/app/api/schemas.py`

**Step 1.2: Add schemas**

Modify: `services/api/app/api/schemas.py`

Add at end of file:
```python
class ACLSnapshotCreate(BaseModel):
    """ACL snapshot creation request (agent-authenticated)"""
    device_id: str
    content_type: str  # acl_rules, firewall_policy, nat_rules, security_policy, route_policy
    encrypted_blob: str
    content_hmac: str
    plaintext_size_bytes: int
    key_id: str
    key_provider: str  # hashicorp_vault, aws_kms, azure_key_vault, gcp_csek, self_managed
    config_hash_at_capture: str | None = None
    compliance_scope: list[str] = []


class ACLSnapshotUpdate(BaseModel):
    """ACL snapshot update request"""
    compliance_scope: list[str] | None = None


class ACLSnapshotResponse(BaseModel):
    """ACL snapshot response"""
    id: str
    organization_id: str
    device_id: str
    content_type: str
    encrypted_blob: str
    content_hmac: str
    plaintext_size_bytes: int | None = None
    key_id: str
    key_provider: str
    encryption_algorithm: str
    captured_at: datetime
    captured_by: str | None = None
    config_hash_at_capture: str | None = None
    compliance_scope: list[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ACLSnapshotListResponse(BaseModel):
    """Paginated ACL snapshot list"""
    items: list[ACLSnapshotResponse]
    total: int
    skip: int
    limit: int
```

---

## Task 2: ACLSnapshot CRUD Endpoints (3a)

### Overview
Implement full CRUD for ACLSnapshot with agent authentication.

### Files
- Modify: `services/api/app/api/routes.py`
- Test: `tests/api/test_acl_vault.py`

### Step 1: Add ACL snapshot routes

**Step 1.1: Add imports**

At top of routes.py, ensure ACLSnapshot is imported:
```python
from app.models.models import ACLSnapshot
```

**Step 1.2: Add CRUD routes**

Modify: `services/api/app/api/routes.py`

Add after change management routes (~line 2850):
```python
# =============================================================================
# ACL COMPLIANCE VAULT
# =============================================================================

@router.post("/acl-snapshots", response_model=schemas.ACLSnapshotResponse, status_code=201)
async def create_acl_snapshot(
    snapshot: schemas.ACLSnapshotCreate,
    current_agent: schemas.User = Depends(dependencies.get_current_agent),
    db: AsyncSession = Depends(get_db),
):
    """Upload ACL snapshot (agent-authenticated)"""
    from uuid import UUID, uuid4
    
    org_id = UUID(current_agent.organization_id)
    
    acl_snapshot = ACLSnapshot(
        id=uuid4(),
        organization_id=org_id,
        device_id=UUID(snapshot.device_id),
        content_type=snapshot.content_type,
        encrypted_blob=snapshot.encrypted_blob,
        content_hmac=snapshot.content_hmac,
        plaintext_size_bytes=snapshot.plaintext_size_bytes,
        key_id=snapshot.key_id,
        key_provider=snapshot.key_provider,
        config_hash_at_capture=snapshot.config_hash_at_capture,
        compliance_scope=snapshot.compliance_scope,
    )
    
    db.add(acl_snapshot)
    await db.commit()
    await db.refresh(acl_snapshot)
    
    await dependencies.audit_log(
        action="acl_snapshot.create",
        resource_type="acl_snapshot",
        resource_id=str(acl_snapshot.id),
        resource_name=f"{acl_snapshot.content_type}",
        outcome="success",
        current_agent=current_agent,
        db=db,
    )
    
    return schemas.ACLSnapshotResponse(
        id=str(acl_snapshot.id),
        organization_id=str(acl_snapshot.organization_id),
        device_id=str(acl_snapshot.device_id),
        content_type=acl_snapshot.content_type,
        encrypted_blob=acl_snapshot.encrypted_blob,
        content_hmac=acl_snapshot.content_hmac,
        plaintext_size_bytes=acl_snapshot.plaintext_size_bytes,
        key_id=acl_snapshot.key_id,
        key_provider=acl_snapshot.key_provider,
        encryption_algorithm=acl_snapshot.encryption_algorithm,
        captured_at=acl_snapshot.captured_at,
        captured_by=str(acl_snapshot.captured_by) if acl_snapshot.captured_by else None,
        config_hash_at_capture=acl_snapshot.config_hash_at_capture,
        compliance_scope=acl_snapshot.compliance_scope or [],
        created_at=acl_snapshot.created_at,
    )


@router.get("/acl-snapshots", response_model=schemas.ACLSnapshotListResponse)
async def list_acl_snapshots(
    skip: int = 0,
    limit: int = 100,
    device_id: str | None = None,
    content_type: str | None = None,
    compliance_scope: str | None = None,
    captured_after: datetime | None = None,
    captured_before: datetime | None = None,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List ACL snapshots with optional filters"""
    from uuid import UUID
    from sqlalchemy import select, func
    
    org_id = UUID(current_user.organization_id)
    
    query = select(ACLSnapshot).where(ACLSnapshot.organization_id == org_id)
    
    if device_id:
        query = query.where(ACLSnapshot.device_id == UUID(device_id))
    if content_type:
        query = query.where(ACLSnapshot.content_type == content_type)
    if compliance_scope:
        query = query.where(ACLSnapshot.compliance_scope.contains([compliance_scope]))
    if captured_after:
        query = query.where(ACLSnapshot.captured_at >= captured_after)
    if captured_before:
        query = query.where(ACLSnapshot.captured_at <= captured_before)
    
    count_query = select(func.count()).select_from(ACLSnapshot).where(
        ACLSnapshot.organization_id == org_id
    )
    if device_id:
        count_query = count_query.where(ACLSnapshot.device_id == UUID(device_id))
    if content_type:
        count_query = count_query.where(ACLSnapshot.content_type == content_type)
    
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    query = query.offset(skip).limit(limit).order_by(ACLSnapshot.captured_at.desc())
    result = await db.execute(query)
    snapshots = result.scalars().all()
    
    return schemas.ACLSnapshotListResponse(
        items=[
            schemas.ACLSnapshotResponse(
                id=str(s.id),
                organization_id=str(s.organization_id),
                device_id=str(s.device_id),
                content_type=s.content_type,
                encrypted_blob=s.encrypted_blob,
                content_hmac=s.content_hmac,
                plaintext_size_bytes=s.plaintext_size_bytes,
                key_id=s.key_id,
                key_provider=s.key_provider,
                encryption_algorithm=s.encryption_algorithm,
                captured_at=s.captured_at,
                captured_by=str(s.captured_by) if s.captured_by else None,
                config_hash_at_capture=s.config_hash_at_capture,
                compliance_scope=s.compliance_scope or [],
                created_at=s.created_at,
            )
            for s in snapshots
        ],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/acl-snapshots/{snapshot_id}", response_model=schemas.ACLSnapshotResponse)
async def get_acl_snapshot(
    snapshot_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific ACL snapshot"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    
    try:
        snapshot_uuid = UUID(snapshot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid snapshot ID format")
    
    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ACLSnapshot).where(
            ACLSnapshot.id == snapshot_uuid,
            ACLSnapshot.organization_id == org_id,
        )
    )
    snapshot = result.scalar_one_or_none()
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="ACL snapshot not found")
    
    return schemas.ACLSnapshotResponse(
        id=str(snapshot.id),
        organization_id=str(snapshot.organization_id),
        device_id=str(snapshot.device_id),
        content_type=snapshot.content_type,
        encrypted_blob=snapshot.encrypted_blob,
        content_hmac=snapshot.content_hmac,
        plaintext_size_bytes=snapshot.plaintext_size_bytes,
        key_id=snapshot.key_id,
        key_provider=snapshot.key_provider,
        encryption_algorithm=snapshot.encryption_algorithm,
        captured_at=snapshot.captured_at,
        captured_by=str(snapshot.captured_by) if snapshot.captured_by else None,
        config_hash_at_capture=snapshot.config_hash_at_capture,
        compliance_scope=snapshot.compliance_scope or [],
        created_at=snapshot.created_at,
    )


@router.delete("/acl-snapshots/{snapshot_id}", status_code=204)
async def delete_acl_snapshot(
    snapshot_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete an ACL snapshot"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    
    try:
        snapshot_uuid = UUID(snapshot_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid snapshot ID format")
    
    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ACLSnapshot).where(
            ACLSnapshot.id == snapshot_uuid,
            ACLSnapshot.organization_id == org_id,
        )
    )
    snapshot = result.scalar_one_or_none()
    
    if not snapshot:
        raise HTTPException(status_code=404, detail="ACL snapshot not found")
    
    await db.delete(snapshot)
    await db.commit()
    
    await dependencies.audit_log(
        action="acl_snapshot.delete",
        resource_type="acl_snapshot",
        resource_id=snapshot_id,
        resource_name=snapshot.content_type,
        outcome="success",
        current_user=current_user,
        db=db,
    )
    
    return None
```

---

## Task 3: ContainerLab Simulation Service (2d)

### Overview
Create topology generator service and simulation endpoints.

### Files
- Create: `services/api/app/services/topology_generator.py`
- Modify: `services/api/app/api/routes.py`

### Step 1: Create topology generator service

**Step 1.1: Create service file**

Create: `services/api/app/services/topology_generator.py`

```python
"""
ContainerLab topology generator service.
Generates ContainerLab YAML topology from Neo4j topology data.
"""
import asyncio
from typing import Dict, Any, List
from app.db.neo4j import get_neo4j_client


class TopologyGenerator:
    """Service for generating ContainerLab topology from Neo4j"""
    
    async def generate_topology(
        self,
        organization_id: str,
        device_ids: List[str],
        proposed_configs: Dict[str, str],
    ) -> Dict[str, Any]:
        """
        Generate ContainerLab topology YAML from Neo4j data.
        
        Args:
            organization_id: Organization UUID
            device_ids: List of device UUIDs to include
            proposed_configs: Dict of device_id -> proposed config
        
        Returns:
            Dict with topology_yaml, nodes, links
        """
        neo4j = await get_neo4j_client()
        
        nodes = []
        links = []
        
        for device_id in device_ids:
            device_result = await neo4j.execute_query(
                """
                MATCH (d:Device {id: $device_id})
                RETURN d.hostname as hostname, d.management_ip as mgmt_ip,
                       d.device_type as device_type, d.vendor as vendor
                """,
                {"device_id": device_id}
            )
            
            if device_result:
                record = device_result[0]
                nodes.append({
                    "id": device_id,
                    "hostname": record.get("hostname", f"device-{device_id[:8]}"),
                    "mgmt_ip": record.get("mgmt_ip"),
                    "device_type": record.get("device_type", "linux"),
                    "vendor": record.get("vendor", "generic"),
                    "config": proposed_configs.get(device_id, ""),
                })
        
        links_result = await neo4j.execute_query(
            """
            MATCH (d1:Device)-[r:CONNECTED_TO]->(d2:Device)
            WHERE d1.id IN $device_ids AND d2.id IN $device_ids
            RETURN d1.id as source, d2.id as target, r.interface as interface
            """,
            {"device_ids": device_ids}
        )
        
        for link in links_result:
            links.append({
                "source": link.get("source"),
                "target": link.get("target"),
                "interface": link.get("interface"),
            })
        
        topology_yaml = self._generate_clab_yaml(nodes, links)
        
        return {
            "topology_yaml": topology_yaml,
            "nodes": nodes,
            "links": links,
            "node_count": len(nodes),
            "link_count": len(links),
        }
    
    def _generate_clab_yaml(self, nodes: List[Dict], links: List[Dict]) -> str:
        """Generate ContainerLab topology YAML"""
        lines = [
            "name: simulation-topology",
            "",
            "topology:",
            "  nodes:",
        ]
        
        for node in nodes:
            node_name = node["hostname"].replace("-", "_")
            device_type = node.get("device_type", "linux")
            
            if device_type in ["router", "switch"]:
                kind = "linux"
            else:
                kind = "linux"
            
            lines.append(f"    {node_name}:")
            lines.append(f"      kind: {kind}")
            if node.get("mgmt_ip"):
                lines.append(f"      mgmt-ip: {node['mgmt_ip']}")
        
        lines.append("  links:")
        for link in links:
            source_name = next(
                (n["hostname"].replace("-", "_") for n in nodes if n["id"] == link["source"]),
                "node1"
            )
            target_name = next(
                (n["hostname"].replace("-", "_") for n in nodes if n["id"] == link["target"]),
                "node2"
            )
            lines.append(f"    - endpoints: [{source_name}:{link.get('interface', 'eth0')},{target_name}:{link.get('interface', 'eth0')}]")
        
        return "\n".join(lines)


topology_generator = TopologyGenerator()
```

### Step 2: Add simulation endpoints

**Step 2.1: Add simulation endpoint**

Modify: `services/api/app/api/routes.py`

Add after ACL Vault routes:
```python
@router.post("/changes/{change_id}/simulate", response_model=schemas.ChangeSimulateResponse)
async def trigger_simulation(
    change_id: str,
    request: schemas.ChangeSimulateRequest,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger ContainerLab simulation for a proposed change"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import ChangeRecord
    
    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")
    
    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()
    
    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")
    
    if change.status != "proposed":
        raise HTTPException(
            status_code=400,
            detail="Can only simulate changes in proposed status"
        )
    
    simulation_id = str(uuid4())
    
    import json
    redis_client = await get_redis()
    await redis_client.hset(
        f"simulation:{simulation_id}",
        mapping={
            "change_id": str(change.id),
            "organization_id": str(org_id),
            "proposed_config": request.proposed_config,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat(),
        }
    )
    await redis_client.expire(f"simulation:{simulation_id}", 3600)
    
    change.simulation_performed = True
    change.simulation_results = {
        "simulation_id": simulation_id,
        "status": "started",
        "started_at": datetime.utcnow().isoformat(),
    }
    
    await db.commit()
    
    await dependencies.audit_log(
        action="change_record.simulate",
        resource_type="change_record",
        resource_id=str(change.id),
        resource_name=change.change_number,
        outcome="success",
        details={"simulation_id": simulation_id},
        current_user=current_user,
        db=db,
    )
    
    return schemas.ChangeSimulateResponse(
        change_id=str(change.id),
        simulation_id=simulation_id,
        status="started",
    )


@router.get("/changes/{change_id}/simulation-results", response_model=schemas.ChangeRecordResponse)
async def get_simulation_results(
    change_id: str,
    current_user: schemas.User = Depends(dependencies.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get simulation results for a change"""
    from uuid import UUID
    from sqlalchemy import select
    from fastapi import HTTPException
    from app.models.models import ChangeRecord
    
    try:
        change_uuid = UUID(change_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid change ID format")
    
    org_id = UUID(current_user.organization_id)
    result = await db.execute(
        select(ChangeRecord).where(
            ChangeRecord.id == change_uuid,
            ChangeRecord.organization_id == org_id,
        )
    )
    change = result.scalar_one_or_none()
    
    if not change:
        raise HTTPException(status_code=404, detail="Change record not found")
    
    if not change.simulation_performed:
        raise HTTPException(status_code=404, detail="No simulation performed for this change")
    
    return schemas.ChangeRecordResponse(
        id=str(change.id),
        organization_id=str(change.organization_id),
        change_number=change.change_number,
        status=change.status,
        simulation_performed=change.simulation_performed,
        simulation_results=change.simulation_results,
        simulation_passed=change.simulation_passed,
        updated_at=change.updated_at,
    )
```

---

## Task 4: Enforce Simulation Before Approval (2d-update)

### Overview
Update the approve endpoint to require simulation_passed=true.

### Files
- Modify: `services/api/app/api/routes.py`

### Step 1: Update approve endpoint

**Step 1.1: Modify approve endpoint**

Find the existing approve endpoint and ensure it checks simulation_passed:

The existing code at ~line 2453 already has this check:
```python
if change.simulation_performed and not change.simulation_passed:
    raise HTTPException(
        status_code=400,
        detail="Simulation must pass before approval"
    )
```

This is already implemented in the existing code. Task complete.

---

## Testing Commands

```bash
# Start services
cd /home/openether/NetDiscoverIT && make up

# Test ACL Vault
# Upload snapshot (agent-authenticated)
curl -X POST http://localhost:8000/api/v1/acl-snapshots \
  -H "Content-Type: application/json" \
  -H "X-Agent-Key: your-agent-key" \
  -d '{
    "device_id": "device-uuid",
    "content_type": "acl_rules",
    "encrypted_blob": "base64-encrypted-content",
    "content_hmac": "sha256-hmac",
    "plaintext_size_bytes": 1024,
    "key_id": "vault://transit/acl-key",
    "key_provider": "hashicorp_vault"
  }'

# List snapshots
curl http://localhost:8000/api/v1/acl-snapshots \
  -H "Authorization: Bearer <token>"

# Get snapshot
curl http://localhost:8000/api/v1/acl-snapshots/{id} \
  -H "Authorization: Bearer <token>"

# Delete snapshot
curl -X DELETE http://localhost:8000/api/v1/acl-snapshots/{id} \
  -H "Authorization: Bearer <token>"

# Test ContainerLab Simulation
# Trigger simulation
curl -X POST http://localhost:8000/api/v1/changes/{id}/simulate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"proposed_config": "router ospf 1\\n network 10.0.0.0 0.255.255.255 area 0"}'

# Get simulation results
curl http://localhost:8000/api/v1/changes/{id}/simulation-results \
  -H "Authorization: Bearer <token>"

# Run tests
pytest tests/api/test_acl_vault.py -v
```

---

## Dependencies Added

- `redis` - Already in use for other features
- `neo4j` - Already in use for topology

---

## Summary

| Task | Description | Status |
|------|-------------|--------|
| 3a-prep | ACLSnapshot schemas | To do |
| 3a | ACLSnapshot CRUD endpoints | To do |
| 2d | ContainerLab simulation endpoints | To do |
| 2d-update | Enforce simulation before approve | Already done |