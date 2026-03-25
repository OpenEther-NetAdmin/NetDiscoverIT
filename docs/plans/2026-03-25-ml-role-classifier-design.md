# Group 6b: ML Device Role Classifier Design

**Created:** 2026-03-25  
**Group:** 6b (ML Pipeline)  
**Status:** Design Review

---

## Overview

The ML Device Role Classifier automatically identifies network device roles (e.g., core_router, firewall, access_switch) based on device metadata collected during discovery. It uses a hybrid approach: rule-based classification for immediate high-confidence results, with ML model training on collected data for enhanced accuracy over time.

---

## Architecture

### Components

1. **RoleClassifier Service** (`services/api/app/services/role_classifier.py`)
   - Main classification logic
   - Rule-based + ML model inference
   - Training data collection

2. **API Endpoints** (`services/api/app/api/routes.py`)
   - `POST /api/v1/devices/{id}/classify` - Trigger classification
   - `GET /api/v1/devices/{id}/classification` - Get current classification
   - `POST /api/v1/devices/classify-batch` - Batch classification

3. **ML Model** (`services/api/app/ml/`)
   - scikit-learn classifier (Random Forest)
   - Model training script
   - Model registry for version management

### Data Flow

**Phase 1 (Manual Classification):**
```
Agent Upload → Device Created → Manual API Call: POST /devices/{id}/classify
                                                              ↓
                                              RoleClassifier.classify()
                                                              ↓
                                              Save to Device.inferred_role
                                                              ↓
                                              Write AuditLog entry
```

**Phase 2 (Auto-classification on upload - Future):**
```
Agent Upload → Device Created → Auto-trigger RoleClassifier.classify()
```

**Note:** Phase 1 uses manual classification via API. Auto-classification on device upload is planned for Phase 2.
Agent Upload → Device Create/Update → RoleClassifier.classify()
                                            ↓
                              ┌─────────────┴─────────────┐
                              ↓                           ↓
                      Rule-Based (fast)           ML Model (if enabled)
                              ↓                           ↓
                      Save to Device.inferred_role   Save to Device.inferred_role
                              ↓                           ↓
                      Collect training data          Collect training data
```

---

## Device Role Taxonomy

Extended taxonomy with 18 roles:

| Role | Description | Key Indicators |
|------|-------------|-----------------|
| `core_router` | Primary routing backbone | High port count, BGP/OSPF, multiple L3 interfaces |
| `edge_router` | WAN edge / ISP connection | WAN interfaces, NAT, routing protocols |
| `distribution_switch` | Layer 3 switching layer | VLANs, routing, many L3 interfaces |
| `access_switch` | User access layer | Many L2 ports, VLANs, PoE |
| `spine_switch` | Clos fabric spine | High bandwidth, leaf connections |
| `leaf_switch` | Clos fabric leaf | Server connections, VXLAN |
| `l2_firewall` | Layer 2 firewall / bridge | Switching, basic ACLs |
| `l3_firewall` | Layer 3 firewall / UTM | NAT, security zones, VPN |
| `load_balancer` | ADC / LBaaS | VIPs, pool members, health checks |
| `server` | Physical/virtual server | OS-type indicators, local services |
| `wireless_controller` | WiFi management | AP management, wireless protocols |
| `access_point` | WiFi access point | Wireless interfaces, PoE |
| `gateway` | Internet gateway | NAT, default route, firewall |
| `datacenter_switch` | DC core switching | High port density, fiber |
| `endpoint_protection` | EDR / network security | Security agent indicators |
| `vpn_concentrator` | Remote access VPN | VPN protocols (IPSec, SSL) |
| `waf` | Web Application Firewall | HTTP inspection, app filtering |
| `domain_controller` | AD / LDAP server | Domain services, LDAP |
| `unknown` | Unclassified | Insufficient data |

---

## Classification Features

### Input Features (from Device.metadata)

| Feature | Type | Description |
|---------|------|-------------|
| `device_type` | categorical | router, switch, firewall, server, etc. |
| `vendor` | categorical | Cisco, Juniper, Fortinet, etc. |
| `interface_count` | numeric | Total interfaces |
| `l3_interface_count` | numeric | Interfaces with IP addresses |
| `vlan_count` | numeric | Number of VLANs |
| `has_bgp` | boolean | BGP configured |
| `has_ospf` | boolean | OSPF configured |
| `has_eigrp` | boolean | EIGRP configured |
| `has_static_routes` | boolean | Static routes configured |
| `acl_count` | numeric | Number of ACLs |
| `nat_enabled` | boolean | NAT configured |
| `vpn_enabled` | boolean | VPN configured |
| `wireless_enabled` | boolean | Wireless features |
| `has_poe` | boolean | PoE capable |
| `port_22_open` | boolean | SSH enabled |
| `port_23_open` | boolean | Telnet enabled |
| `port_161_open` | boolean | SNMP enabled |
| `port_443_open` | boolean | HTTPS enabled |
| `port_80_open` | boolean | HTTP enabled |

---

## Output Storage

### Primary Storage (New Columns)

```python
# In Device model - canonical store
inferred_role = Column(String(50), nullable=True)  # role from taxonomy
role_confidence = Column(Float, nullable=True)     # 0.0 - 1.0 confidence
role_classified_at = Column(DateTime, nullable=True)  # classification timestamp
role_classifier_version = Column(String(20), nullable=True)  # model version

# Note: Device.meta JSONB is NOT used for classification results - only the dedicated columns above
```

**Note:** Classification results are stored ONLY in the dedicated columns above. The Device.meta JSONB column is NOT used as a fallback to avoid dual source of truth.

---

## Implementation Phases

### Phase 1: Rule-Based Classifier (Priority: High)

- Implement rule-based classification logic
- Define rules for each role in the taxonomy
- Target: 80%+ classification coverage

### Phase 2: ML Model (Priority: Medium)

- **Important:** The Device model already has `role_vector = Column(Vector(768))` populated by Group 6a vectorizer
- The Phase 2 ML classifier should use pgvector nearest-neighbor search against a labeled device set as the primary approach
- Fallback: train Random Forest classifier on extracted features
- Implement model versioning and registry
- Target: 90%+ accuracy on validation set

### Phase 3: Continuous Learning (Priority: Low)

- Feedback loop for user corrections
- Periodic model retraining
- A/B testing between rule-based and ML

---

## API Endpoints

### POST /api/v1/devices/{id}/classify

Trigger classification for a single device.

**Request:**
```json
{}
```

**Response:**
```json
{
  "inferred_role": "core_router",
  "confidence": 0.92,
  "classified_at": "2026-03-25T12:00:00Z",
  "method": "rule_based",
  "features": {
    "interface_count": 48,
    "l3_interface_count": 4,
    "has_bgp": true
  }
}
```

### GET /api/v1/devices/{id}/classification

Get current classification for a device.

**Response:**
```json
{
  "inferred_role": "core_router",
  "confidence": 0.92,
  "classified_at": "2026-03-25T12:00:00Z",
  "classifier_version": "1.0.0"
}
```

### POST /api/v1/devices/classify-batch

Batch classify multiple devices.

**Request:**
```json
{
  "device_ids": ["uuid1", "uuid2", "uuid3"]
}
```

---

## Error Handling

| Scenario | Behavior |
|----------|----------|
| Insufficient features | Return `unknown` role, confidence = 0.0 |
| ML model unavailable | Fall back to rule-based |
| Classification failure | Return 500, log error |
| Invalid device ID | Return 404 |

---

## Testing Strategy

1. **Unit Tests** - Rule logic, feature extraction
2. **Integration Tests** - API endpoints, DB storage
3. **Model Tests** - Accuracy, precision, recall per role
4. **E2E Tests** - Full classification flow

---

## Security Considerations

- No raw device configs stored in classifier
- Classification uses only sanitized metadata
- Audit log on all classification operations

---

## Dependencies

- scikit-learn (ML model)
- pandas (data processing)
- numpy (vector operations)
- sqlalchemy (DB)
- FastAPI (API)

---

## References

- Group 6a Vectorizer: `2026-03-23-group6a-vectorizer-design.md`
- Phase 2 Work Plan: `/tmp/claw-memory/phase2-work-plan.md`