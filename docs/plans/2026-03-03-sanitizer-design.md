# Config Sanitizer Design

**Date:** 2026-03-03  
**Component:** Local Agent — Config Sanitizer Module  
**Status:** Design Approved

---

## Overview

The Config Sanitizer ensures **zero sensitive data leaves the customer network**. It processes raw device configurations before they reach the vectorizer, replacing identifiable information with placeholder tokens while preserving structural patterns for ML training.

This is a **critical privacy component** — the product cannot operate without it.

---

## Architecture

### Data Flow

```
Raw Config Text (from Collector)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                     ConfigSanitizer                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────┐ │
│  │   Tier 1        │  │   Tier 2        │  │  Tier 3      │ │
│  │  TextFSM Parse  │→ │ Section Regex   │→ │ Aggressive   │ │
│  │  (if template)  │  │ (if no template)│  │ Regex Only   │ │
│  │                 │  │                 │  │ (fallback)   │ │
│  └─────────────────┘  └─────────────────┘  └──────────────┘ │
│           │                    │                    │       │
│           └────────────────────┴────────────────────┘       │
│                              │                              │
│                              ▼                              │
│         ┌────────────────────────────────────┐              │
│         │    Token Replacement Engine        │              │
│         │  • <ip_address>, <ipv6_address>    │              │
│         │  • <hostname>, <fqdn>              │              │
│         │  • <community_string>              │              │
│         │  • <password>, <secret>, <key>     │              │
│         │  • <as_number>, <vlan_id>          │              │
│         │  • <mac_address>                   │              │
│         └────────────────────────────────────┘              │
│                              │                              │
└──────────────────────────────┼──────────────────────────────┘
                               │
                               ▼
              ┌──────────────────────────────┐
              │  Sanitized Text (vectorizer) │
              └──────────────────────────────┘
                               │
                               ▼
              ┌──────────────────────────────┐
              │  Redaction Map (audit log)   │
              │  • what was replaced         │
              │  • line numbers              │
              │  • replacement type          │
              └──────────────────────────────┘
```

### Multi-Tenancy Isolation

The Local Agent architecture provides **strong isolation by default**:

- **Stateless Processing**: Each config sanitized independently, no shared state
- **No Cross-Contamination**: Each customer runs separate Local Agent container
- **Deterministic Tokens**: Same pattern → always same token (no randomization)
- **Per-Org Audit Trail**: Redaction maps tagged with org_id for accountability

---

## Components

### ConfigSanitizer (Main Entry Point)

```python
class ConfigSanitizer:
    """Main entry point for config sanitization"""
    
    def __init__(self, org_id: str, enable_llm: bool = False):
        self.org_id = org_id
        self.tier_resolver = TierResolver()
        self.token_mapper = TokenMapper()
        self.redaction_logger = RedactionLogger(org_id)
        self.llm_fallback = LLMSanitizer() if enable_llm else None
    
    async def sanitize(self, config_text: str, device_type: str) -> SanitizerResult:
        """
        Returns:
            sanitized_text: Token-replaced config for vectorizer
            redaction_map: Audit trail of replacements
            metadata: Tier used, template matched, stats
        """
```

### TierResolver

Determines sanitization strategy based on available resources:

| Tier | Trigger | Method |
|------|---------|--------|
| **Tier 1** | TextFSM template exists | Parse → redact by field name → re-serialize |
| **Tier 2** | No template, but structured | Section-aware regex patterns |
| **Tier 3** | Unstructured/unknown | Aggressive regex catch-all |
| **LLM** | Enabled by customer | Optional fallback for ambiguous cases |

### TokenMapper

Maps data types to standardized placeholder tokens:

| Data Type | Token | Example |
|-----------|-------|---------|
| IPv4 Address | `<ip_address>` | `10.1.1.1` → `<ip_address>` |
| IPv6 Address | `<ipv6_address>` | `2001:db8::1` → `<ipv6_address>` |
| Hostname | `<hostname>` | `router-core-01` → `<hostname>` |
| FQDN | `<fqdn>` | `core01.example.com` → `<fqdn>` |
| Password | `<password>` | `password Cisco123` → `password <password>` |
| Secret | `<secret>` | `secret 5 $1$abc...` → `secret <secret>` |
| Community | `<community_string>` | `snmp-server community public` → `snmp-server community <community_string>` |
| BGP AS | `<as_number>` | `router bgp 65001` → `router bgp <as_number>` |
| VLAN ID | `<vlan_id>` | `vlan 100` → `vlan <vlan_id>` |
| MAC Address | `<mac_address>` | `0011.2233.4455` → `<mac_address>` |

### RedactionLogger

Creates cryptographically-verified audit trail:

```json
{
  "replacements": [
    {
      "type": "ipv4",
      "line": 15,
      "original_hash": "sha256:abc...",
      "token": "<ip_address>"
    },
    {
      "type": "password",
      "line": 23,
      "original_hash": "sha256:def...",
      "token": "<password>"
    }
  ],
  "tier_used": 1,
  "template_matched": "cisco_ios",
  "sanitized_at": "2026-03-03T12:00:00Z"
}
```

---

## Error Handling

### Fail-Safe Principles

1. **Never fail open**: If sanitization fails, block upload — never expose raw config
2. **Graceful degradation**: Fall back through tiers, but always apply Tier 3 as last resort
3. **Safety verification**: Post-sanitization scan to catch missed patterns
4. **Explicit errors**: Clear messages for operators when manual intervention needed

### Error Scenarios

| Scenario | Response |
|----------|----------|
| No TextFSM template | Fallback to Tier 2 |
| Parse error | Fallback to Tier 3 |
| Tier 3 misses sensitive data | **Block upload** + alert |
| LLM enabled but Ollama unreachable | Log warning, proceed without LLM |
| Binary/non-text data | Reject with clear error |

### Safety Check Example

```python
def _safety_scan(self, text: str) -> bool:
    """Verify no obvious sensitive data remains after sanitization"""
    # Check for unredacted IPv4 addresses
    if re.search(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', text):
        return False
    # Check for password literals
    if re.search(r'password\s+\S+', text, re.IGNORECASE):
        return False
    return True
```

---

## LLM Integration (Optional)

**Disabled by default** — customers must explicitly opt-in via configuration.

```yaml
# local-agent-config.yaml
sanitizer:
  enable_llm_fallback: false  # Default: false
  ollama_model: "llama3.2:7b"
  ollama_url: "http://localhost:11434"
```

**When LLM is used:**
- Only for ambiguous cases where regex confidence is low
- Local Ollama instance — no data leaves customer network
- Can suggest new regex patterns for future improvement

**Why opt-in?**
- Some customers don't want *any* process seeing raw configs
- LLM adds latency and resource usage
- Deterministic regex is auditable; LLM is not

---

## Testing Strategy

### Test Categories

| Category | Coverage |
|----------|----------|
| **Unit Tests** | Individual tiers, token mapper, redaction logger |
| **Integration Tests** | Full pipeline with real configs per vendor |
| **Safety Tests** | Verify blocked if sanitization fails |
| **Performance Tests** | Large configs, concurrent processing |

### Test Fixtures

```
tests/agent/fixtures/
configs/
    cisco_ios/
        router_base.cfg          # Standard case
        router_no_template.cfg   # Tier 2 trigger
        switch_complex.cfg       # VLANs, routing
        firewall_asa.cfg         # Security config
    juniper_junos/
        router_base.cfg
    arista_eos/
        switch_base.cfg
    f5_ltm/
        ltm_base.cfg
    corrupted/
        binary_data.cfg          # Rejection test
        minified.cfg             # Edge case
        empty.cfg                # Edge case
```

### Critical Safety Test

```python
async def test_sanitizer_blocks_on_failure():
    """Ensure raw config never leaks if sanitization fails"""
    sanitizer = ConfigSanitizer(org_id="test-org")
    
    # Config with sensitive data in unparseable format
    tricky_config = "password\x00hidden\x00in\x00binary"
    
    with pytest.raises(SanitizationError):
        await sanitizer.sanitize(tricky_config, "unknown_device")
```

---

## Configuration

```yaml
# services/agent/config/sanitizer.yaml
sanitizer:
  # Tier selection
  prefer_textfsm: true
  fallback_to_regex: true
  
  # LLM (opt-in only)
  enable_llm: false
  ollama_url: "http://localhost:11434"
  ollama_model: "llama3.2:7b"
  
  # Safety
  safety_check_enabled: true
  block_on_failure: true
  
  # Performance
  max_config_size_mb: 50
  timeout_seconds: 30
  
  # Tokens (customizable)
  tokens:
    ipv4: "<ip_address>"
    ipv6: "<ipv6_address>"
    hostname: "<hostname>"
    password: "<password>"
    secret: "<secret>"
    community: "<community_string>"
    bgp_as: "<as_number>"
    vlan_id: "<vlan_id>"
    mac: "<mac_address>"
```

---

## Integration Points

### Input (from Collector)
- Raw config text (string)
- Device type hint (for template selection)
- Org ID (for audit logging)

### Output (to Vectorizer)
- Sanitized text with placeholder tokens
- Redaction map (audit trail)
- Metadata (tier used, processing time, stats)

### Dependencies
- `ntc-templates` — TextFSM templates for Tier 1
- `textfsm` — Parsing library
- `ollama` (optional) — LLM fallback

---

## Success Criteria

1. **Privacy**: Zero raw credentials or sensitive identifiers in vectorizer output
2. **Coverage**: 100% of configs processed (no silent failures)
3. **Performance**: < 100ms for configs up to 10K lines
4. **Auditability**: Complete redaction map for every sanitization
5. **Reliability**: 99.9% uptime (deterministic processing)

---

## Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| LLM required? | No — regex/TextFSM primary, LLM opt-in only |
| How to handle unknown configs? | Tiered fallback with safety block |
| Cross-tenant isolation? | Stateless processing + per-org agents |
| What gets tokenized? | Credentials (strip) + identifiers (replace) |

---

## Implementation Notes

- Start with Tier 2 (section regex) for immediate coverage
- Add Tier 1 (TextFSM) incrementally per vendor
- Tier 3 (aggressive regex) as fail-safe
- LLM integration last, behind explicit flag

---

**Approved by:** Product Owner  
**Next Step:** Create implementation plan via `writing-plans` skill
