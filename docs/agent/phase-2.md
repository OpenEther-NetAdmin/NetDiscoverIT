# Phase 2 Implementation Guidelines

## Overview

Phase 2 focuses on completing the agent service with scanning, discovery, and integration capabilities.

## Key Modules to Implement

### Scanner Module (`services/agent/agent/scanner.py`)
- Network discovery via SSH, SNMP, Nmap
- Device identification and classification
- Integration with existing sanitizer

### Collector Module (`services/agent/agent/collector.py`)
- Config collection from network devices
- Change detection via config diffing

### Topology Module (`services/agent/agent/topology.py`)
- Network topology mapping (CDP/LLDP)
- Relationship discovery between devices

### IVRE Integration (`services/agent/agent/ivre_integration.py`)
- Network recon framework integration
- Nmap results parsing

## Consistency Rules

1. **All code must work in Docker containers** - never on local machine
2. **Use existing patterns** - follow sanitizer module structure
3. **Update memory repo** - document all decisions in claw-memory
4. **Add tests** - unit tests for new modules
5. **Use type hints** - Python 3.9+ compatible

## Code Structure

```
services/agent/
├── agent/
│   ├── __init__.py
│   ├── main.py              # Entry point
│   ├── config.py            # Configuration
│   ├── scanner.py           # Network scanning
│   ├── collector.py         # Config collection
│   ├── topology.py          # Topology mapping
│   ├── sanitizer/           # Existing - don't modify
│   └── ...
└── tests/agent/
    └── ...
```

## Privacy First

Remember: Raw device configs NEVER leave customer network. The sanitizer must process all data before any upload.
