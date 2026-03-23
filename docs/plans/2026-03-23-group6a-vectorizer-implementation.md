# Group 6a: Vectorizer Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Upgrade local agent vectorizer to use sentence-transformers/all-mpnet-base-v2 (768-dim) and add config_vector from normalized config text.

**Architecture:** Incremental update to existing vectorizer.py, update API schemas to accept new vector, update upload endpoint to store vectors. All vector generation on-prem.

**Tech Stack:** sentence-transformers, pgvector, FastAPI, SQLAlchemy

---

## Dependencies

- **Group 5 (TextFSM Normalization):** Must be complete first — config_vector requires normalized config output
- **sentence-transformers package:** Already installed (==3.3.1 in requirements.txt)

---

## Task 1: Verify sentence-transformers in Agent Requirements

**Files:**
- Verify: `services/agent/requirements.txt`

**Step 1: Verify dependency exists**

Check that `sentence-transformers` is in requirements.txt:
```
sentence-transformers==3.3.1
```

This is already installed (==3.3.1, better than >=2.2.0). No changes needed.

**Step 2: Commit (if any changes)**

```bash
git add services/agent/requirements.txt
git commit -m "deps: verify sentence-transformers for vectorizer"
```

---

## Task 2: Update Agent Vectorizer Model

**Files:**
- Modify: `services/agent/agent/vectorizer.py`
- Test: `services/agent/tests/test_vectorizer.py` (create if not exists)

**Step 1: Write failing test**

Create `services/agent/tests/test_vectorizer.py`:

```python
import pytest
from agent.vectorizer import DeviceVectorizer

class TestVectorizerDimensions:
    @pytest.fixture
    def vectorizer(self):
        config = {}
        return DeviceVectorizer(config)

    @pytest.mark.asyncio
    async def test_role_vector_is_768_dims(self, vectorizer):
        metadata = {"hostname": "test-switch", "vendor": "Cisco", "device_type": "switch"}
        vectors = await vectorizer.generate_vectors(metadata)
        assert len(vectors['device_role']) == 768

    @pytest.mark.asyncio
    async def test_topology_vector_is_768_dims(self, vectorizer):
        metadata = {"interfaces": [{"name": "Gi0/1"}]}
        vectors = await vectorizer.generate_vectors(metadata)
        assert len(vectors['topology']) == 768

    @pytest.mark.asyncio
    async def test_security_vector_is_768_dims(self, vectorizer):
        metadata = {"acls": ["acl1"]}
        vectors = await vectorizer.generate_vectors(metadata)
        assert len(vectors['security']) == 768

    @pytest.mark.asyncio
    async def test_config_vector_is_768_dims(self, vectorizer):
        metadata = {"normalized_config": {"interfaces": [{"name": "Gi0/1"}]}}
        vectors = await vectorizer.generate_vectors(metadata)
        assert len(vectors['config']) == 768
```

**Step 2: Run test to verify it fails**

```bash
cd services/agent && python -m pytest tests/test_vectorizer.py -v
Expected: FAIL - vectors have wrong dimensions or config key missing
```

**Step 3: Write implementation**

Update `services/agent/agent/vectorizer.py`:

```python
"""
Device Vectorizer
Generates embeddings for ML analysis
"""

import logging
import json
from typing import Dict, List

logger = logging.getLogger(__name__)


class DeviceVectorizer:
    """Generates vector embeddings for devices"""
    
    MODEL_NAME = 'sentence-transformers/all-mpnet-base-v2'
    VECTOR_DIM = 768
    
    def __init__(self, config):
        self.config = config
        self._model = None
    
    @property
    def model(self):
        """Lazy load model - load once, reuse across devices"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.MODEL_NAME)
            except ImportError:
                logger.warning("sentence-transformers not available")
                self._model = None
        return self._model
    
    async def generate_vectors(self, device_metadata: Dict) -> Dict:
        """Generate vector embeddings for a device"""
        vectors = {}
        
        vectors['device_role'] = await self._generate_role_vector(device_metadata)
        vectors['topology'] = await self._generate_topology_vector(device_metadata)
        vectors['security'] = await self._generate_security_vector(device_metadata)
        vectors['config'] = await self._generate_config_vector(device_metadata)
        
        return vectors
    
    async def _generate_role_vector(self, metadata: Dict) -> List[float]:
        """Generate device role vector"""
        if self.model is None:
            return self._rule_based_role_vector(metadata)
        
        description = self._build_role_description(metadata)
        embedding = self.model.encode(description)
        return embedding.tolist()
    
    async def _generate_topology_vector(self, metadata: Dict) -> List[float]:
        """Generate topology-related vector"""
        if self.model is None:
            return self._rule_based_topology_vector(metadata)
        
        description = self._build_topology_description(metadata)
        embedding = self.model.encode(description)
        return embedding.tolist()
    
    async def _generate_security_vector(self, metadata: Dict) -> List[float]:
        """Generate security posture vector"""
        if self.model is None:
            return self._rule_based_security_vector(metadata)
        
        description = self._build_security_description(metadata)
        embedding = self.model.encode(description)
        return embedding.tolist()
    
    async def _generate_config_vector(self, metadata: Dict) -> List[float]:
        """Generate configuration similarity vector from normalized config"""
        if self.model is None:
            return self._rule_based_config_vector(metadata)
        
        description = self._build_config_description(metadata)
        embedding = self.model.encode(description)
        return embedding.tolist()
    
    def _build_role_description(self, metadata: Dict) -> str:
        """Build text description for role classification"""
        parts = []
        
        if 'hostname' in metadata:
            parts.append(f"Device hostname: {metadata['hostname']}")
        
        if 'vendor' in metadata:
            parts.append(f"Vendor: {metadata['vendor']}")
        
        if 'device_type' in metadata:
            parts.append(f"Type: {metadata['device_type']}")
        
        interfaces = metadata.get('interfaces', [])
        if interfaces:
            parts.append(f"Has {len(interfaces)} interfaces")
        
        if 'routing' in metadata:
            parts.append("Supports routing protocols")
        
        vendor = metadata.get('vendor', '').lower()
        if 'firewall' in metadata.get('device_type', '').lower() or 'palo' in vendor or 'fortinet' in vendor:
            parts.append("Security appliance")
        
        return ". ".join(parts)
    
    def _build_topology_description(self, metadata: Dict) -> str:
        """Build text description for topology"""
        parts = []
        
        interfaces = metadata.get('interfaces', [])
        vlans = metadata.get('vlans', [])
        
        if interfaces:
            layer3 = sum(1 for i in interfaces if i.get('ip_address'))
            layer2 = len(interfaces) - layer3
            parts.append(f"{layer3} L3 interfaces, {layer2} L2 interfaces")
        
        if vlans:
            parts.append(f"Member of {len(vlans)} VLANs")
        
        return ". ".join(parts) if parts else "Standard network device"
    
    def _build_security_description(self, metadata: Dict) -> str:
        """Build text description for security"""
        parts = []
        
        if metadata.get('acls'):
            parts.append(f"Has {len(metadata.get('acls', []))} ACLs")
        
        if metadata.get('nat'):
            parts.append("Uses NAT")
        
        if metadata.get('zones'):
            parts.append(f"Has {len(metadata.get('zones', []))} security zones")
        
        return ". ".join(parts) if parts else "Standard security configuration"
    
    def _build_config_description(self, metadata: Dict) -> str:
        """Build text description from normalized config for similarity search"""
        normalized_config = metadata.get('normalized_config')
        
        if not normalized_config:
            return "No configuration available"
        
        parts = []
        
        if isinstance(normalized_config, dict):
            parts.append(self._serialize_config_dict(normalized_config))
        elif isinstance(normalized_config, str):
            parts.append(normalized_config)
        
        return " ".join(parts)
    
    def _serialize_config_dict(self, config: Dict, prefix: str = "") -> str:
        """Recursively serialize config dict to deterministic string"""
        parts = []
        
        for key in sorted(config.keys()):
            value = config[key]
            
            if isinstance(value, dict):
                parts.append(self._serialize_config_dict(value, f"{prefix}{key}."))
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        parts.append(self._serialize_config_dict(item, f"{prefix}{key}."))
                    else:
                        parts.append(f"{prefix}{key}={item}")
            else:
                parts.append(f"{prefix}{key}={value}")
        
        return " ".join(parts)
    
    def _rule_based_role_vector(self, metadata: Dict) -> List[float]:
        """Generate rule-based role vector as fallback"""
        import hashlib
        
        vector = [0.0] * self.VECTOR_DIM
        
        seed = int(hashlib.md5(metadata.get('hostname', '').encode()).hexdigest()[:8], 16)
        
        for i in range(min(len(vector), self.VECTOR_DIM)):
            vector[i] = ((seed * (i + 1)) % 1000) / 1000.0
        
        return vector
    
    def _rule_based_topology_vector(self, metadata: Dict) -> List[float]:
        return [0.0] * self.VECTOR_DIM
    
    def _rule_based_security_vector(self, metadata: Dict) -> List[float]:
        return [0.0] * self.VECTOR_DIM
    
    def _rule_based_config_vector(self, metadata: Dict) -> List[float]:
        return [0.0] * self.VECTOR_DIM
```

**Step 4: Run test to verify it passes**

```bash
cd services/agent && python -m pytest tests/test_vectorizer.py -v
Expected: PASS (all 4 tests)
```

**Step 5: Commit**

```bash
git add services/agent/agent/vectorizer.py services/agent/tests/test_vectorizer.py
git commit -m "feat(vectorizer): upgrade to all-mpnet-base-v2 (768-dim) and add config_vector"
```

---

## Task 3: Update API Schema for config_vector

**Files:**
- Modify: `services/api/app/api/schemas.py`

**Step 1: Update VectorData schema**

In `services/api/app/api/schemas.py`, find `class VectorData` and add:

```python
class VectorData(BaseModel):
    """Vector data for a device"""

    device_role: List[float]
    topology: List[float]
    security: List[float]
    config: List[float]  # NEW: configuration similarity vector
```

**Step 2: Update DeviceMetadataUpload to accept vectors**

Find `class DeviceMetadataUpload` and add optional vector fields:

```python
class DeviceMetadataUpload(BaseModel):
    """Device metadata from agent upload"""
    hostname: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    device_type: str | None = None
    vendor: str | None = None
    model: str | None = None
    os_version: str | None = None
    site_id: str | None = None
    metadata: dict = {}
    config_hash: str | None = None
    config_collected_at: datetime | None = None
    # NEW: Vector fields
    role_vector: List[float] | None = None
    topology_vector: List[float] | None = None
    security_vector: List[float] | None = None
    config_vector: List[float] | None = None
```

**Step 3: Commit**

```bash
git add services/api/app/api/schemas.py
git commit -m "feat(api): add config_vector and optional vector fields to upload schema"
```

---

## Task 4: Update Upload Endpoint to Store Vectors

**Files:**
- Modify: `services/api/app/api/routes.py`

**Step 1: Write failing test**

Create `services/api/tests/test_upload_with_vectors.py`:

```python
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_upload_with_vectors():
    async with AsyncClient(app=app, base_url="http://test") as client:
        payload = {
            "devices": [
                {
                    "hostname": "test-router",
                    "ip_address": "10.0.0.1",
                    "device_type": "router",
                    "vendor": "Cisco",
                    "role_vector": [0.1] * 768,
                    "topology_vector": [0.2] * 768,
                    "security_vector": [0.3] * 768,
                    "config_vector": [0.4] * 768
                }
            ]
        }
        response = await client.post(
            "/api/v1/agents/test-agent-id/upload",
            json=payload,
            headers={"X-Agent-Key": "test-key"}
        )
        assert response.status_code in [200, 201]
```

**Step 2: Run test to verify it fails**

```bash
cd services/api && python -m pytest tests/test_upload_with_vectors.py -v
Expected: FAIL - vectors not handled
```

**Step 3: Update upload endpoint**

In `services/api/app/api/routes.py`, find `upload_agent_data` function and update the device creation/update logic:

```python
# In the device update/create section, after setting other fields:
if device_data.role_vector is not None:
    existing.role_vector = device_data.role_vector
if device_data.topology_vector is not None:
    existing.topology_vector = device_data.topology_vector
if device_data.security_vector is not None:
    existing.security_vector = device_data.security_vector
if device_data.config_vector is not None:
    existing.config_vector = device_data.config_vector
```

For new device creation, add vector fields to the Device constructor.

**Step 4: Run test to verify it passes**

```bash
cd services/api && python -m pytest tests/test_upload_with_vectors.py -v
Expected: PASS
```

**Step 5: Commit**

```bash
git add services/api/app/api/routes.py services/api/tests/test_upload_with_vectors.py
git commit -m "feat(api): store vectors in upload endpoint"
```

---

## Task 5: Integration Test - Full Pipeline

**Files:**
- Test: `services/agent/tests/test_full_vectorizer_pipeline.py` (create)

**Step 1: Create integration test**

```python
import pytest
from agent.vectorizer import DeviceVectorizer

class TestFullVectorizerPipeline:
    @pytest.fixture
    def vectorizer(self):
        config = {}
        return DeviceVectorizer(config)
    
    @pytest.fixture
    def sample_metadata(self):
        """Sample metadata as would come from normalizer + sanitizer.

        Note: IP addresses shown are illustrative. In production, these would be
        tokenized by the sanitizer before reaching the vectorizer (e.g., <ip_address>).
        """
        return {
            "hostname": "core-router-01",
            "vendor": "Cisco",
            "device_type": "router",
            "interfaces": [
                {"name": "Gi0/0", "ip_address": "10.0.0.1"},
                {"name": "Gi0/1", "ip_address": "10.0.1.1"},
                {"name": "Gi0/2"},  # L2 interface
            ],
            "vlans": [10, 20, 30],
            "routing": {"bgp": True, "ospf": False},
            "acls": ["ACL-001", "ACL-002"],
            "nat": True,
            "normalized_config": {
                "interfaces": [
                    {"name": "Gi0/0", "ip": "10.0.0.1", "mask": "255.255.255.0"},
                    {"name": "Gi0/1", "ip": "10.0.1.1", "mask": "255.255.255.0"}
                ],
                "bgp": {"asn": 65001, "neighbor_count": 1}  # Neighbor IPs stripped by sanitizer
            }
        }
    
    @pytest.mark.asyncio
    async def test_all_vectors_generated(self, vectorizer, sample_metadata):
        vectors = await vectorizer.generate_vectors(sample_metadata)
        
        assert 'device_role' in vectors
        assert 'topology' in vectors
        assert 'security' in vectors
        assert 'config' in vectors
        
        for vec_name, vec in vectors.items():
            assert len(vec) == 768, f"{vec_name} should be 768 dims"
    
    @pytest.mark.asyncio
    async def test_deterministic_output(self, vectorizer, sample_metadata):
        """Same input should produce same output"""
        vectors1 = await vectorizer.generate_vectors(sample_metadata)
        vectors2 = await vectorizer.generate_vectors(sample_metadata)
        
        for vec_name in vectors1:
            assert vectors1[vec_name] == vectors2[vec_name], f"{vec_name} should be deterministic"
```

**Step 2: Run integration test**

```bash
cd services/agent && python -m pytest tests/test_full_vectorizer_pipeline.py -v
Expected: PASS
```

**Step 3: Commit**

```bash
git add services/agent/tests/test_full_vectorizer_pipeline.py
git commit -m "test: add integration tests for full vectorizer pipeline"
```

---

## Task 6: Run Full Test Suite and Lint

**Step 1: Run all tests**

```bash
make test
Expected: All tests pass
```

**Step 2: Run lint**

```bash
make lint
Expected: No lint errors
```

**Step 3: Commit any remaining changes**

```bash
git add -A
git commit -m "chore: pass full test suite and lint"
```

---

## Summary

| Task | Files | Effort |
|------|-------|--------|
| 1. Verify sentence-transformers | requirements.txt | 2 min |
| 2. Update vectorizer | vectorizer.py + tests | 1.5 hr |
| 3. Update API schema | schemas.py | 15 min |
| 4. Update upload endpoint | routes.py + tests | 1 hr |
| 5. Integration test | tests | 30 min |
| 6. Test + lint | all | 15 min |
| **Total** | | ~4 hr |

---

## Plan complete and saved to `docs/plans/2026-03-23-group6a-vectorizer-implementation.md`.

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?