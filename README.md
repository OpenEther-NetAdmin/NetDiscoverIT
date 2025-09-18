# NetDiscoverIT

Network discovery tool for SMB ITIL compliance. Scans, identifies, categorizes, and generates docs/diagrams.

## Quick Start
1. `poetry install`
2. `poetry run netdiscoverit scan 192.168.1.0/24 --output-dir results/`
3. `poetry run netdiscoverit generate-docs results/scan_results.json --template itil_cmdb`

## Modules
- `scanner/`: Nmap/Scapy discovery
- `identifier/`: SNMP OS/vendor ID (stub next)
- etc. (Add via plugins)

## Next: Implement identifier/categorizer stubs?
License: MIT