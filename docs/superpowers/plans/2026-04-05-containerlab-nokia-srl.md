# Containerlab Nokia SR Linux Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the NetDiscoverIT agent able to collect, normalize, and discover topology from Nokia SR Linux devices running in Containerlab, plus add local Containerlab dev targets to the Makefile.

**Architecture:** Nokia SR Linux uses a fundamentally different CLI from Cisco (no `show running-config`, no `show ip interface brief`). Three separate hardcoded `device_type_map` dicts in `collector.py` and `topology.py` all need `nokia_srl` added. TextFSM templates for SR Linux go in `services/agent/agent/templates/` (the fallback dir that `textfsm_parser.py` already checks). Normalizer vendor detection needs to recognize SR Linux output markers.

**Tech Stack:** Netmiko `nokia_srl` device type, TextFSM, pytest with fixture strings, Containerlab CLI, Nokia SR Linux 24.10.1

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `services/agent/agent/templates/nokia_srl_show_version.textfsm` | Create | Parse `show version` output |
| `services/agent/agent/templates/nokia_srl_show_interface.textfsm` | Create | Parse `show interface` tabular output |
| `services/agent/agent/templates/nokia_srl_show_lldp_neighbor.textfsm` | Create | Parse `show lldp neighbor` for topology edges |
| `services/agent/agent/normalizer_textfsm/textfsm_parser.py` | Modify | Add `nokia_srl` to TEMPLATE_MAP |
| `services/agent/agent/normalizer.py` | Modify | Add Nokia to `_detect_vendor` and `_get_vendor_key` |
| `services/agent/agent/collector.py` | Modify | Add `nokia` to device_type_map; add Nokia-specific SSH commands |
| `services/agent/agent/topology.py` | Modify | Add `nokia` to device_type_map in `_discover_lldp` and `SwitchMapperIntegration`; add SR Linux LLDP parse |
| `tests/agent/test_nokia_srl.py` | Create | Unit tests with SR Linux output fixtures |
| `Makefile` | Modify | Add `clab-up`, `clab-down`, `clab-status` targets |

---

### Task 1: TextFSM Templates for Nokia SR Linux

**Files:**
- Create: `services/agent/agent/templates/nokia_srl_show_version.textfsm`
- Create: `services/agent/agent/templates/nokia_srl_show_interface.textfsm`
- Create: `services/agent/agent/templates/nokia_srl_show_lldp_neighbor.textfsm`

These templates parse actual SR Linux CLI output. SR Linux uses a key: value format for `show version` and a table format for interfaces and LLDP. Templates must match Containerlab SR Linux 24.10.1 output exactly.

- [ ] **Step 1: Create the templates directory**

```bash
mkdir -p services/agent/agent/templates
```

- [ ] **Step 2: Create nokia_srl_show_version.textfsm**

SR Linux `show version` output format:
```
--------------------------------------------------------------------------------
Hostname      : spine1
Chassis Type  : 7220 IXR-D2L
Part Number   : Sim Part No.
Serial Number : Sim Serial No.
System HW MAC : 1A:2B:3C:4D:5E:6F
OS            : SR Linux
Software Version : v24.10.1
Kernel Version : 5.15.0
Build Number  : 348-gabcdef01
Last Booted   : 2024-01-01T00:00:00.000Z
Total Memory  : 24366980 kB
Free Memory   : 22000000 kB
--------------------------------------------------------------------------------
```

```textfsm
# services/agent/agent/templates/nokia_srl_show_version.textfsm
Value HOSTNAME (\S+)
Value CHASSIS_TYPE (.+?)
Value SERIAL_NUMBER (\S+)
Value OS (.+?)
Value SW_VERSION (\S+)
Value KERNEL_VERSION (\S+)
Value TOTAL_MEMORY (\d+)

Start
  ^Hostname\s+:\s+${HOSTNAME}
  ^Chassis\s+Type\s+:\s+${CHASSIS_TYPE}
  ^Serial\s+Number\s+:\s+${SERIAL_NUMBER}
  ^OS\s+:\s+${OS}
  ^Software\s+Version\s+:\s+${SW_VERSION}
  ^Kernel\s+Version\s+:\s+${KERNEL_VERSION}
  ^Total\s+Memory\s+:\s+${TOTAL_MEMORY}
  ^-{10,} -> Record
```

- [ ] **Step 3: Create nokia_srl_show_interface.textfsm**

SR Linux `show interface` tabular output:
```
+---+---------------------------+-----+-------+--------------------+
|   | Interface Name            | Oper| Admin | IPv4 Address       |
|   |                           |State| State |                    |
+===+===========================+=====+=======+====================+
|   | ethernet-1/1              | up  | up    | -                  |
|   | ethernet-1/2              | up  | up    | -                  |
|   | mgmt0                     | up  | up    | 172.20.20.3/24     |
|   | system0                   | up  | up    | 127.0.0.1/8        |
+---+---------------------------+-----+-------+--------------------+
```

```textfsm
# services/agent/agent/templates/nokia_srl_show_interface.textfsm
Value INTERFACE (\S+)
Value OPER_STATE (up|down)
Value ADMIN_STATE (up|down)
Value IPV4_ADDRESS (\S+)

Start
  ^\|\s+\|\s+${INTERFACE}\s+\|\s+${OPER_STATE}\s+\|\s+${ADMIN_STATE}\s+\|\s+${IPV4_ADDRESS}\s+\| -> Record
  ^\|\s+${INTERFACE}\s+\|\s+${OPER_STATE}\s+\|\s+${ADMIN_STATE}\s+\|\s+${IPV4_ADDRESS}\s+\| -> Record
```

- [ ] **Step 4: Create nokia_srl_show_lldp_neighbor.textfsm**

SR Linux `show lldp neighbor` tabular output:
```
+------------------------------------------------------------------+
|                      LLDP Neighbor Summary                       |
+--------------+------------------+------------------+-----+------+
| Interface    | Neighbor System  | Neighbor Port ID | TTL | Caps |
+==============+==================+==================+=====+======+
| ethernet-1/1 | leaf1            | ethernet-1/49    | 110 | B,R  |
| ethernet-1/2 | leaf2            | ethernet-1/49    | 110 | B,R  |
+--------------+------------------+------------------+-----+------+
```

```textfsm
# services/agent/agent/templates/nokia_srl_show_lldp_neighbor.textfsm
Value LOCAL_INTERFACE (\S+)
Value NEIGHBOR_SYSTEM (\S+)
Value NEIGHBOR_PORT (\S+)
Value TTL (\d+)

Start
  ^\|\s+${LOCAL_INTERFACE}\s+\|\s+${NEIGHBOR_SYSTEM}\s+\|\s+${NEIGHBOR_PORT}\s+\|\s+${TTL}\s+\| -> Record
```

- [ ] **Step 5: Commit**

```bash
git add services/agent/agent/templates/
git commit -m "feat(agent): add TextFSM templates for Nokia SR Linux (version, interface, lldp)"
```

---

### Task 2: Wire Nokia into TextFSMParser

**Files:**
- Modify: `services/agent/agent/normalizer_textfsm/textfsm_parser.py:13-20`
- Test: `tests/agent/test_nokia_srl.py`

- [ ] **Step 1: Write the failing test first**

Create `tests/agent/test_nokia_srl.py`:

```python
"""
Tests for Nokia SR Linux TextFSM template parsing.
All sample outputs are representative of actual Nokia SR Linux 24.10.1 CLI output
from Containerlab-provisioned nodes.
"""
import pytest

SAMPLE_SRL_SHOW_VERSION = """\
--------------------------------------------------------------------------------
Hostname      : spine1
Chassis Type  : 7220 IXR-D2L
Part Number   : Sim Part No.
Serial Number : SIM12345678
System HW MAC : 1A:2B:3C:4D:5E:6F
OS            : SR Linux
Software Version : v24.10.1
Kernel Version : 5.15.0
Build Number  : 348-gabcdef01
Last Booted   : 2024-01-01T00:00:00.000Z
Total Memory  : 24366980 kB
Free Memory   : 22000000 kB
--------------------------------------------------------------------------------
"""

SAMPLE_SRL_SHOW_INTERFACE = """\
+---+---------------------------+-----+-------+--------------------+
|   | Interface Name            | Oper| Admin | IPv4 Address       |
|   |                           |State| State |                    |
+===+===========================+=====+=======+====================+
|   | ethernet-1/1              | up  | up    | -                  |
|   | ethernet-1/2              | down| up    | -                  |
|   | mgmt0                     | up  | up    | 172.20.20.3/24     |
+---+---------------------------+-----+-------+--------------------+
"""

SAMPLE_SRL_SHOW_LLDP_NEIGHBOR = """\
+--------------+------------------+------------------+-----+------+
| Interface    | Neighbor System  | Neighbor Port ID | TTL | Caps |
+==============+==================+==================+=====+======+
| ethernet-1/1 | leaf1            | ethernet-1/49    | 110 | B,R  |
| ethernet-1/2 | leaf2            | ethernet-1/49    | 110 | B,R  |
+--------------+------------------+------------------+-----+------+
"""


class TestNokiaSRLTextFSM:
    def test_parse_show_version_returns_hostname(self):
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        parser = TextFSMParser()
        result = parser.parse(SAMPLE_SRL_SHOW_VERSION, "nokia_srl")
        assert result.get("hostname") == "spine1"

    def test_parse_show_version_returns_sw_version(self):
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        parser = TextFSMParser()
        result = parser.parse(SAMPLE_SRL_SHOW_VERSION, "nokia_srl")
        assert "v24.10.1" in result.get("sw_version", "")

    def test_parse_show_version_method_tag(self):
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        parser = TextFSMParser()
        result = parser.parse(SAMPLE_SRL_SHOW_VERSION, "nokia_srl")
        assert result.get("_normalization_method") == "textfsm"

    def test_parse_show_interface_finds_mgmt0(self):
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        parser = TextFSMParser()
        result = parser.parse(SAMPLE_SRL_SHOW_INTERFACE, "nokia_srl_interface")
        assert result.get("interface") == "mgmt0" or "mgmt0" in str(result)

    def test_parse_lldp_neighbor_finds_leaf1(self):
        from agent.normalizer_textfsm.textfsm_parser import TextFSMParser
        parser = TextFSMParser()
        result = parser.parse(SAMPLE_SRL_SHOW_LLDP_NEIGHBOR, "nokia_srl_lldp")
        assert "leaf1" in str(result)
```

- [ ] **Step 2: Run to confirm it fails**

```bash
docker compose exec api pytest tests/agent/test_nokia_srl.py::TestNokiaSRLTextFSM::test_parse_show_version_returns_hostname -v
```

Expected: `FAILED` — `AssertionError` (returns empty dict, no template found)

- [ ] **Step 3: Update TEMPLATE_MAP in textfsm_parser.py**

In `services/agent/agent/normalizer_textfsm/textfsm_parser.py`, the `TEMPLATE_MAP` dict at lines 13-20 currently reads:

```python
    TEMPLATE_MAP = {
        "cisco_ios": "cisco_ios_show_version.textfsm",
        "cisco_nxos": "cisco_nxos_show_version.textfsm",
        "juniper_junos": "junos_show_version.textfsm",
        "arista_eos": "arista_eos_show_version.textfsm",
        "hp_procurve": "hp_procurve_show_version.textfsm",
        "f5_bigip": "f5_bigip_version.textfsm",
    }
```

Replace with:

```python
    TEMPLATE_MAP = {
        "cisco_ios": "cisco_ios_show_version.textfsm",
        "cisco_nxos": "cisco_nxos_show_version.textfsm",
        "juniper_junos": "junos_show_version.textfsm",
        "arista_eos": "arista_eos_show_version.textfsm",
        "hp_procurve": "hp_procurve_show_version.textfsm",
        "f5_bigip": "f5_bigip_version.textfsm",
        "nokia_srl": "nokia_srl_show_version.textfsm",
        "nokia_srl_interface": "nokia_srl_show_interface.textfsm",
        "nokia_srl_lldp": "nokia_srl_show_lldp_neighbor.textfsm",
    }
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
docker compose exec api pytest tests/agent/test_nokia_srl.py -v
```

Expected: All 5 tests `PASSED`

If any fail due to template regex not matching the fixture strings, adjust the `.textfsm` file `Value` patterns to match the exact fixture whitespace. The fixture strings in the test are the source of truth.

- [ ] **Step 5: Commit**

```bash
git add services/agent/agent/normalizer_textfsm/textfsm_parser.py tests/agent/test_nokia_srl.py
git commit -m "feat(agent): add nokia_srl to TextFSMParser TEMPLATE_MAP, add SRL unit tests"
```

---

### Task 3: Nokia Vendor Detection in Normalizer

**Files:**
- Modify: `services/agent/agent/normalizer.py:79-88` and `217-232`
- Test: `tests/agent/test_nokia_srl.py` (extend)

SR Linux output is identified by the string `"SR Linux"` appearing in `show version` output.

- [ ] **Step 1: Add failing tests for vendor detection**

Append to `tests/agent/test_nokia_srl.py`:

```python
class TestNokiaSRLVendorDetection:
    def test_detect_vendor_from_show_version(self):
        from agent.normalizer import ConfigNormalizer
        from unittest.mock import MagicMock
        normalizer = ConfigNormalizer(MagicMock())
        vendor = normalizer._detect_vendor(SAMPLE_SRL_SHOW_VERSION)
        assert vendor == "nokia"

    def test_get_vendor_key_nokia(self):
        from agent.normalizer import ConfigNormalizer
        from unittest.mock import MagicMock
        normalizer = ConfigNormalizer(MagicMock())
        key = normalizer._get_vendor_key("nokia")
        assert key == "nokia_srl"
```

- [ ] **Step 2: Run to confirm failure**

```bash
docker compose exec api pytest tests/agent/test_nokia_srl.py::TestNokiaSRLVendorDetection -v
```

Expected: `FAILED` — `assert 'unknown' == 'nokia'`

- [ ] **Step 3: Update `_detect_vendor` in normalizer.py**

In `services/agent/agent/normalizer.py`, `_detect_vendor` (lines 217-232) currently ends at `return "unknown"`. Add Nokia detection before that return:

```python
    def _detect_vendor(self, config: str) -> str:
        """Detect vendor from config"""
        config_lower = config.lower()

        if "cisco" in config_lower or "ios" in config_lower:
            return "cisco"
        elif "juniper" in config_lower or "junos" in config_lower:
            return "juniper"
        elif "arista" in config_lower or "eos" in config_lower:
            return "arista"
        elif "f5" in config_lower:
            return "f5"
        elif "palo alto" in config_lower:
            return "palo_alto"
        elif "sr linux" in config_lower or "nokia" in config_lower:
            return "nokia"

        return "unknown"
```

- [ ] **Step 4: Update `_get_vendor_key` in normalizer.py**

In `services/agent/agent/normalizer.py`, `_get_vendor_key` (lines 79-88):

```python
    def _get_vendor_key(self, vendor: str) -> str:
        """Map detected vendor to TextFSM template key"""
        vendor_map = {
            "cisco": "cisco_ios",
            "juniper": "juniper_junos",
            "arista": "arista_eos",
            "f5": "f5_bigip",
            "hp": "hp_procurve",
            "nokia": "nokia_srl",
        }
        return vendor_map.get(vendor.lower(), "")
```

- [ ] **Step 5: Run tests**

```bash
docker compose exec api pytest tests/agent/test_nokia_srl.py -v
```

Expected: All 7 tests `PASSED`

- [ ] **Step 6: Commit**

```bash
git add services/agent/agent/normalizer.py tests/agent/test_nokia_srl.py
git commit -m "feat(agent): add Nokia SR Linux vendor detection and vendor key mapping"
```

---

### Task 4: Nokia SSH Commands in Collector

**Files:**
- Modify: `services/agent/agent/collector.py:112-158`
- Test: `tests/agent/test_nokia_srl.py` (extend)

SR Linux CLI commands differ fundamentally from Cisco. `show running-config` does not exist — the equivalent is `info` (returns YANG-structured config). Interface info uses `show interface`. The collector currently hardcodes Cisco commands for all vendors.

- [ ] **Step 1: Add failing test for Nokia SSH command selection**

Append to `tests/agent/test_nokia_srl.py`:

```python
class TestNokiaSRLCollector:
    def test_nokia_maps_to_nokia_srl_device_type(self):
        """Collector must select nokia_srl Netmiko device type for nokia vendor"""
        from agent.collector import DeviceCollector
        from unittest.mock import MagicMock
        collector = DeviceCollector(MagicMock(SSH_TIMEOUT=30))
        device_type = collector._get_netmiko_device_type("nokia")
        assert device_type == "nokia_srl"

    def test_nokia_ssh_commands_not_cisco(self):
        """Nokia devices must not receive Cisco-specific commands"""
        from agent.collector import DeviceCollector
        from unittest.mock import MagicMock
        collector = DeviceCollector(MagicMock(SSH_TIMEOUT=30))
        commands = collector._get_ssh_commands("nokia")
        # SR Linux does not have 'show running-config' or 'show ip interface brief'
        command_str = " ".join(commands)
        assert "show running-config" not in command_str
        assert "show ip interface brief" not in command_str
        assert "show interface" in command_str
```

- [ ] **Step 2: Run to confirm failure**

```bash
docker compose exec api pytest tests/agent/test_nokia_srl.py::TestNokiaSRLCollector -v
```

Expected: `FAILED` — `AttributeError: 'DeviceCollector' object has no attribute '_get_netmiko_device_type'`

- [ ] **Step 3: Refactor collector.py to extract device type + command logic**

In `services/agent/agent/collector.py`, the `_get_config_ssh` method currently has the `device_type_map` inline. Refactor it to add two extracted methods, then update `_get_config_ssh` to use them. The complete changes to the file:

**Add these two methods** to `DeviceCollector` class, before `_get_config_ssh`:

```python
    def _get_netmiko_device_type(self, vendor: str) -> str:
        """Map vendor string to Netmiko device_type."""
        device_type_map = {
            'cisco': 'cisco_ios',
            'juniper': 'juniper_junos',
            'arista': 'arista_eos',
            'f5': 'f5_ltm',
            'palo alto': 'paloalto_panos',
            'nokia': 'nokia_srl',
        }
        return device_type_map.get(vendor.lower(), 'cisco_ios')

    def _get_ssh_commands(self, vendor: str) -> list:
        """Return the list of show commands to run for this vendor."""
        vendor_lower = vendor.lower()
        if vendor_lower == 'nokia':
            return [
                'show version',
                'show interface',
                'show lldp neighbor',
            ]
        # Default: Cisco-style commands (also works for Arista/most vendors)
        return [
            'show running-config',
            'show version',
            'show ip interface brief',
            'show vlan',
        ]
```

**Update `_get_config_ssh`** to use the extracted methods. Replace the body of the method (lines 104-162) with:

```python
    async def _get_config_ssh(self, device: Dict) -> str:
        """Get config via SSH using Netmiko"""
        try:
            from netmiko import ConnectHandler

            credentials = device.get('credentials', {})
            vendor = device.get('vendor', 'cisco_ios').lower()
            device_type = self._get_netmiko_device_type(vendor)

            conn = {
                'device_type': device_type,
                'host': device['management_ip'],
                'username': credentials.get('username'),
                'password': credentials.get('password'),
                'secret': credentials.get('enable_password', ''),
                'timeout': self.config.SSH_TIMEOUT,
            }

            logger.info(f"Connecting to {device['hostname']} ({device['management_ip']}) as {device_type}")

            netmiko_conn = ConnectHandler(**conn)

            if conn['secret']:
                netmiko_conn.enable()

            commands = self._get_ssh_commands(vendor)
            sections = []
            for cmd in commands:
                output = netmiko_conn.send_command(cmd)
                sections.append(f"=== {cmd.upper()} ===\n{output}")

            netmiko_conn.disconnect()

            return "\n\n".join(sections)

        except Exception as e:
            logger.error(f"SSH config retrieval failed for {device['hostname']}: {e}")
            raise
```

- [ ] **Step 4: Run tests**

```bash
docker compose exec api pytest tests/agent/test_nokia_srl.py -v
```

Expected: All 9 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add services/agent/agent/collector.py tests/agent/test_nokia_srl.py
git commit -m "feat(agent): refactor collector SSH to support Nokia SRL commands; extract device_type + commands helpers"
```

---

### Task 5: Nokia Support in Topology Discovery

**Files:**
- Modify: `services/agent/agent/topology.py:44-51`, `484-491`
- Test: `tests/agent/test_nokia_srl.py` (extend)

`topology.py` has two separate `device_type_map` dicts (in `_discover_lldp` and `SwitchMapperIntegration.discover_topology`) that both miss `nokia`. Also, `_parse_lldp_output` uses `"Chassis ID:"` / `"System Name:"` key parsing which is Cisco LLDP format — SR Linux LLDP output is a table and won't match.

- [ ] **Step 1: Add failing test**

Append to `tests/agent/test_nokia_srl.py`:

```python
SAMPLE_SRL_LLDP_DETAIL = """\
+--------------+------------------+------------------+-----+------+
| Interface    | Neighbor System  | Neighbor Port ID | TTL | Caps |
+==============+==================+==================+=====+======+
| ethernet-1/1 | leaf1            | ethernet-1/49    | 110 | B,R  |
| ethernet-1/2 | leaf2            | ethernet-1/49    | 110 | B,R  |
+--------------+------------------+------------------+-----+------+
"""

class TestNokiaSRLTopology:
    def test_parse_srl_lldp_output_finds_neighbors(self):
        from agent.topology import TopologyDiscovery
        from unittest.mock import MagicMock
        td = TopologyDiscovery(MagicMock(SSH_TIMEOUT=30))
        neighbors = td._parse_srl_lldp_output(SAMPLE_SRL_LLDP_DETAIL)
        assert len(neighbors) == 2

    def test_parse_srl_lldp_output_neighbor_hostnames(self):
        from agent.topology import TopologyDiscovery
        from unittest.mock import MagicMock
        td = TopologyDiscovery(MagicMock(SSH_TIMEOUT=30))
        neighbors = td._parse_srl_lldp_output(SAMPLE_SRL_LLDP_DETAIL)
        hostnames = [n['hostname'] for n in neighbors]
        assert 'leaf1' in hostnames
        assert 'leaf2' in hostnames

    def test_parse_srl_lldp_output_local_interface(self):
        from agent.topology import TopologyDiscovery
        from unittest.mock import MagicMock
        td = TopologyDiscovery(MagicMock(SSH_TIMEOUT=30))
        neighbors = td._parse_srl_lldp_output(SAMPLE_SRL_LLDP_DETAIL)
        local_ifs = [n['local_interface'] for n in neighbors]
        assert 'ethernet-1/1' in local_ifs
```

- [ ] **Step 2: Run to confirm failure**

```bash
docker compose exec api pytest tests/agent/test_nokia_srl.py::TestNokiaSRLTopology -v
```

Expected: `FAILED` — `AttributeError: 'TopologyDiscovery' object has no attribute '_parse_srl_lldp_output'`

- [ ] **Step 3: Update `_discover_lldp` device_type_map in topology.py**

In `services/agent/agent/topology.py`, the `device_type_map` inside `_discover_lldp` (around line 46) currently:

```python
            device_type_map = {
                'cisco': 'cisco_ios',
                'juniper': 'juniper_junos',
                'arista': 'arista_eos',
            }
            device_type = device_type_map.get(vendor, 'cisco_ios')
```

Replace with:

```python
            device_type_map = {
                'cisco': 'cisco_ios',
                'juniper': 'juniper_junos',
                'arista': 'arista_eos',
                'nokia': 'nokia_srl',
            }
            device_type = device_type_map.get(vendor, 'cisco_ios')
```

- [ ] **Step 4: Update `SwitchMapperIntegration.discover_topology` device_type_map in topology.py**

Around line 486-491, same pattern — replace with:

```python
        device_type_map = {
            'cisco': 'cisco_ios',
            'juniper': 'juniper_junos',
            'arista': 'arista_eos',
            'nokia': 'nokia_srl',
        }
        device_type = device_type_map.get(vendor, 'cisco_ios')
```

- [ ] **Step 5: Add `_parse_srl_lldp_output` method to `TopologyDiscovery`**

In `services/agent/agent/topology.py`, add this method to the `TopologyDiscovery` class, after `_parse_lldp_output` (around line 182):

```python
    def _parse_srl_lldp_output(self, output: str) -> List[Dict]:
        """Parse Nokia SR Linux 'show lldp neighbor' table output.

        Expected format:
          | ethernet-1/1 | leaf1  | ethernet-1/49  | 110 | B,R |
        """
        neighbors = []
        for line in output.split('\n'):
            line = line.strip()
            # Match data rows: start and end with '|', not separator rows ('+-...-+')
            if not line.startswith('|') or line.startswith('+-') or '===' in line:
                continue
            parts = [p.strip() for p in line.split('|') if p.strip()]
            # Expect at least: local_intf, neighbor_system, neighbor_port, ttl
            if len(parts) < 4:
                continue
            local_intf, neighbor_system, neighbor_port = parts[0], parts[1], parts[2]
            # Skip header rows (contain non-interface text like "Interface")
            if local_intf.lower() in ('interface', 'neighbor system', ''):
                continue
            neighbors.append({
                'local_interface': local_intf,
                'hostname': neighbor_system,
                'port_id': neighbor_port,
                'protocol': 'lldp',
            })
        return neighbors
```

- [ ] **Step 6: Use `_parse_srl_lldp_output` in `_discover_lldp` for Nokia devices**

In `_discover_lldp`, after the block that runs LLDP commands (around line 74-83), the current code checks `if output and "LLDP" in output`. For Nokia, the SR Linux LLDP command is simply `show lldp neighbor`. Update the block to route Nokia parsing differently:

Find the existing LLDP command loop in `_discover_lldp`:

```python
            for cmd in lldp_commands:
                try:
                    output = netmiko_conn.send_command(cmd, timeout=10)
                    if output and "LLDP" in output:
                        parsed = self._parse_lldp_output(output)
                        for n in parsed:
                            n['protocol'] = 'lldp'
                        neighbors.extend(parsed)
                        break
                except Exception as e:
                    logger.debug(f"LLDP command '{cmd}' failed: {e}")
                    continue
```

Replace with:

```python
            if vendor == 'nokia':
                try:
                    output = netmiko_conn.send_command('show lldp neighbor', timeout=10)
                    if output:
                        neighbors.extend(self._parse_srl_lldp_output(output))
                except Exception as e:
                    logger.debug(f"Nokia LLDP command failed: {e}")
            else:
                lldp_commands = [
                    "show lldp neighbors detail",
                    "show lldp neighbors",
                    "show lldp entry *",
                ]
                for cmd in lldp_commands:
                    try:
                        output = netmiko_conn.send_command(cmd, timeout=10)
                        if output and "LLDP" in output:
                            parsed = self._parse_lldp_output(output)
                            for n in parsed:
                                n['protocol'] = 'lldp'
                            neighbors.extend(parsed)
                            break
                    except Exception as e:
                        logger.debug(f"LLDP command '{cmd}' failed: {e}")
                        continue
```

- [ ] **Step 7: Run all Nokia tests**

```bash
docker compose exec api pytest tests/agent/test_nokia_srl.py -v
```

Expected: All 12 tests `PASSED`

- [ ] **Step 8: Run full agent test suite to confirm no regressions**

```bash
docker compose exec api pytest tests/agent/ -v
```

Expected: All tests pass. Any failures are pre-existing, not caused by these changes.

- [ ] **Step 9: Commit**

```bash
git add services/agent/agent/topology.py tests/agent/test_nokia_srl.py
git commit -m "feat(agent): add Nokia SR Linux LLDP discovery and SRL-specific neighbor table parser"
```

---

### Task 6: Local Containerlab Dev Targets

**Files:**
- Modify: `Makefile`

These targets let developers run Containerlab locally to test the agent without GCP. They use the topology file already defined in the Terraform plan at `infra/gcp/clab/topology.yml`. Containerlab must be installed locally (`curl -sL https://get.containerlab.dev | bash`).

- [ ] **Step 1: Add Containerlab section to Makefile**

Add after the `# GCP TEST ENVIRONMENT` section (or at the end of the file if that section hasn't been added yet):

```makefile
# =============================================================================
# LOCAL CONTAINERLAB (dev testing without GCP)
# =============================================================================
# Prerequisites: Containerlab installed (curl -sL https://get.containerlab.dev | bash)
# Images: Nokia SR Linux pulls automatically from ghcr.io/nokia/srlinux:24.10.1
# Note: Requires Docker and sudo or a user in the 'docker' group.
# =============================================================================
CLAB_TOPO ?= infra/gcp/clab/topology.yml

clab-up:
	sudo containerlab deploy -t $(CLAB_TOPO) --reconfigure
	@echo ""
	@echo "Containerlab topology running. Get node IPs with: make clab-status"
	@echo "SSH into spine1: ssh admin@\$$(sudo containerlab inspect -t $(CLAB_TOPO) --format json | python3 -c \"import sys,json; [print(c['IPv4Address'].split('/')[0]) for c in json.load(sys.stdin)['Containers'] if 'spine1' in c['Name']]\")"
	@echo "Password: NokiaSrl1!"

clab-down:
	sudo containerlab destroy -t $(CLAB_TOPO) --cleanup

clab-status:
	sudo containerlab inspect -t $(CLAB_TOPO)

clab-ssh-spine1:
	@IP=$$(sudo containerlab inspect -t $(CLAB_TOPO) --format json | python3 -c "import sys,json; [print(c['IPv4Address'].split('/')[0]) for c in json.load(sys.stdin)['Containers'] if 'spine1' in c['Name']]") && ssh admin@$$IP

clab-ssh-leaf1:
	@IP=$$(sudo containerlab inspect -t $(CLAB_TOPO) --format json | python3 -c "import sys,json; [print(c['IPv4Address'].split('/')[0]) for c in json.load(sys.stdin)['Containers'] if 'leaf1' in c['Name']]") && ssh admin@$$IP
```

- [ ] **Step 2: Add clab entries to help target**

In the `help:` target in `Makefile`, add these lines inside the `@echo` block:

```makefile
	@echo ""
	@echo "Local Containerlab (dev):"
	@echo "  $(YELLOW)clab-up$(NC)         - Deploy SR Linux spine-leaf topology locally"
	@echo "  $(YELLOW)clab-down$(NC)       - Destroy local Containerlab topology"
	@echo "  $(YELLOW)clab-status$(NC)     - Show running nodes and IPs"
	@echo "  $(YELLOW)clab-ssh-spine1$(NC) - SSH into spine1"
	@echo "  $(YELLOW)clab-ssh-leaf1$(NC)  - SSH into leaf1"
```

- [ ] **Step 3: Commit**

```bash
git add Makefile
git commit -m "feat(infra): add local Containerlab Makefile targets (clab-up, clab-down, clab-status)"
```

---

### Task 7: End-to-End Verification (Local)

This task validates everything works together against a real running Containerlab topology. It requires Containerlab installed locally and Docker running.

- [ ] **Step 1: Start Containerlab**

```bash
make clab-up
```

Expected: 5 containers running (spine1, spine2, leaf1, leaf2, server1). Takes 2-3 minutes for SR Linux to boot.

- [ ] **Step 2: Verify SSH reachability**

```bash
make clab-status
# Note the mgmt IP of spine1 (e.g., 172.20.20.3)
ssh admin@172.20.20.3  # password: NokiaSrl1!
```

Expected: SR Linux interactive CLI prompt: `A:spine1#`

- [ ] **Step 3: Verify show commands work**

Inside the SR Linux SSH session:

```
A:spine1# show version
A:spine1# show interface
A:spine1# show lldp neighbor
```

Expected:
- `show version`: Shows "SR Linux", hostname "spine1"
- `show interface`: Shows ethernet-1/1, ethernet-1/2 (up after ~60s), mgmt0
- `show lldp neighbor`: Shows leaf1 and leaf2 as neighbors (LLDP needs ~30s to populate)

- [ ] **Step 4: Create a local agent test config**

Create `configs/agent-clab-local.yaml` (copy the contents, filling in actual IPs from `make clab-status`):

```yaml
VERSION: "0.1.0"

API_KEY: "test-key"
API_ENDPOINT: "http://localhost:8000"

DISCOVERY_METHODS:
  - ssh
  - lldp

SCAN_INTERVAL: "1h"
SSH_TIMEOUT: 30
LOG_LEVEL: "debug"

devices:
  - hostname: spine1
    ip: "172.20.20.3"   # replace with actual IP from make clab-status
    type: router
    vendor: nokia
    methods: [ssh]
    credentials:
      username: admin
      password: NokiaSrl1!

  - hostname: spine2
    ip: "172.20.20.4"   # replace with actual IP
    type: router
    vendor: nokia
    methods: [ssh]
    credentials:
      username: admin
      password: NokiaSrl1!
```

- [ ] **Step 5: Run agent against Containerlab (--once mode)**

```bash
docker compose run --rm \
  -v $(pwd)/configs/agent-clab-local.yaml:/app/config/agent.yaml:ro \
  agent python -m agent.main --once
```

Expected agent log output:
```
INFO Connecting to spine1 (172.20.20.3) as nokia_srl
INFO Successfully normalized using TextFSM for vendor: nokia
INFO Upload successful: {...}
```

- [ ] **Step 6: Stop Containerlab when done**

```bash
make clab-down
```

- [ ] **Step 7: Commit agent-clab-local config example**

```bash
git add configs/agent-clab-local.yaml
git commit -m "feat(infra): add local Containerlab agent config example"
```

---

## Verification Checklist

After all tasks complete:

1. `docker compose exec api pytest tests/agent/test_nokia_srl.py -v` → 12 tests PASSED
2. `docker compose exec api pytest tests/agent/ -v` → no regressions
3. `make clab-up && make clab-status` → 5 SR Linux containers running
4. `ssh admin@<spine1-ip>` → SR Linux CLI accessible, `show lldp neighbor` shows leaf1/leaf2
5. Agent run against Containerlab shows TextFSM normalization (not LLM fallback) in logs
6. After agent run: `curl localhost:8000/api/v1/devices` returns Nokia SR Linux devices with structured metadata

## Not In Scope

- Arista cEOS integration (requires Arista account for image download)
- SNMP collection from SR Linux (SNMP requires additional Containerlab config beyond scope here)
- Containerlab CI integration (running clab in GitHub Actions requires self-hosted runners)
- SR Linux gNMI/gRPC collection (Phase 2 — SSH is sufficient for current metadata schema)
