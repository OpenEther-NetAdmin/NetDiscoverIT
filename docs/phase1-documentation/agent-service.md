# Agent Service

The Agent Service is the on-premises component of NetDiscoverIT that runs within the customer's network. It handles all device interactions, configuration collection, and critically, data sanitization before any information is transmitted to the cloud. This document covers the agent's architecture, modules, and how to work with the codebase.

## Running the Agent

The agent runs as a Docker container alongside other services. All development and testing must occur within containers, never on the local machine.

## Core Modules

### Scanner Module

**File:** `services/agent/agent/scanner.py`

The Scanner module initiates network discovery by probing target networks for reachable devices. It supports multiple discovery methods and identifies device characteristics.

**Key functions:**

- `discover_network()` - Main entry point for network scanning
- `discover_via_ssh()` - SSH-based device discovery
- `discover_via_snmp()` - SNMP-based device discovery
- `discover_via_nmap()` - Nmap port scanning

The scanner returns device metadata including vendor, model, operating system version, and management IP addresses.

### Collector Module

**File:** `services/agent/agent/collector.py`

The Collector module retrieves running configurations from discovered devices. It uses SSH to connect to devices and execute commands that dump current configurations.

**Key functions:**

- `collect_config()` - Collect configuration from a single device
- `collect_all()` - Orchestrate collection across multiple devices
- `get_device_type()` - Determine device vendor/type from SSH response

The collector passes raw configurations directly to the sanitizer for processing. It never stores unencrypted configurations on disk.

### Sanitizer Module

**File:** `services/agent/agent/sanitizer/`

The Sanitizer is the most critical component in the agent. It strips all sensitive information from configurations before any data leaves the customer network. This module implements the privacy guarantee.

**Architecture:**

The sanitizer uses a tiered approach for comprehensive coverage:

- **Tier 1 (TextFSMSanitizer):** Uses TextFSM templates for precise, vendor-specific parsing. Located at `sanitizer/tiers/tier1_textfsm.py`.
- **Tier 2 (SectionRegexSanitizer):** Applies section-aware regex patterns. Located at `sanitizer/tiers/tier2_section.py`.
- **Tier 3 (AggressiveRegexSanitizer):** Catch-all patterns for remaining data. Located at `sanitizer/tiers/tier3_regex.py`.

**Main class:** `ConfigSanitizer` at `sanitizer/config_sanitizer.py`

**Usage:**

```python
from agent.sanitizer import ConfigSanitizer

sanitizer = ConfigSanitizer(org_id="your-org-id")
result = sanitizer.sanitize(raw_config, device_type="cisco_ios")

sanitized_config = result["sanitized"]
redaction_log = result["redaction_log"]
```

**Token System:**

The tokenizer maps sensitive data types to placeholder tokens. Defined in `sanitizer/token_mapper.py` with TokenType enum values like IPV4, PASSWORD, SECRET, COMMUNITY, BGP_AS, VLAN_ID, MAC_ADDRESS.

**Redaction Logging:**

The RedactionLogger tracks what was redacted without storing actual values. Located at `sanitizer/redaction_logger.py`. It stores SHA-256 hashes for verification.

**Tier Resolution:**

TierResolver determines which tier to use based on device type and configuration structure. Located at `sanitizer/tier_resolver.py`.

### Topology Module

**File:** `services/agent/agent/topology.py`

The Topology module discovers network relationships by parsing CDP and LLDP neighbor information. It builds a graph of device connections.

**Key functions:**

- `discover_topology()` - Main entry point for topology discovery
- `parse_cdp_neighbors()` - Parse CDP data from Cisco devices
- `parse_lldp_neighbors()` - Parse LLDP data from standard devices
- `build_topology_graph()` - Construct graph data structure

### Vectorizer Module

**File:** `services/agent/agent/vectorizer.py`

The Vectorizer generates embeddings from sanitized configurations. It uses sentence transformers to convert text to numerical vectors.

**Key functions:**

- `generate_embedding()` - Generate embedding from configuration text
- `batch_generate()` - Generate embeddings for multiple configurations

The vectorizer produces 768-dimensional embeddings compatible with pgvector storage.

### Uploader Module

**File:** `services/agent/agent/uploader.py`

The Uploader transmits processed data to the API service. It handles authentication and retry logic.

**Key functions:**

- `upload_discovery()` - Upload sanitized discovery data
- `upload_topology()` - Upload topology relationships
- `upload_embeddings()` - Upload vector embeddings

## Configuration

The agent loads configuration from YAML files and environment variables. See `services/agent/agent/config.py` for the configuration model.

**Key settings:**

- `API_ENDPOINT` - URL of the API service
- `API_KEY` - Authentication key
- `DISCOVERY_METHODS` - Methods to use for discovery (ssh, snmp, nmap)
- `SCAN_INTERVAL` - How often to run discovery scans
- `SSH_TIMEOUT` - Timeout for SSH connections
- `SNMP_TIMEOUT` - Timeout for SNMP queries

## Development

When developing agent code, follow these guidelines:

1. **Work in containers** - All development happens in Docker containers
2. **Use type hints** - Python 3.9+ compatible type annotations
3. **Add tests** - Unit tests go in `tests/agent/`
4. **Update memory** - Document changes in claw-memory repo

## Testing

Run tests using the containerized test environment:

```bash
make test
```

Test fixtures for the sanitizer are located in `tests/agent/fixtures/`.