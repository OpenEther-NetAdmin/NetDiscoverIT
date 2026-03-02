"""
Topology Discovery Module
Discovers network topology using CDP, LLDP, and other protocols
Integrates: arp-scan, switch-mapper, fprobe
"""

import asyncio
import logging
import subprocess
import json
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class TopologyDiscovery:
    """Discover network topology via CDP/LLDP"""
    
    def __init__(self, config):
        self.config = config
    
    async def discover_neighbors(self, device: Dict) -> List[Dict]:
        """Discover neighbors via CDP and LLDP"""
        neighbors = []
        
        # Try LLDP first (vendor-neutral)
        lldp_neighbors = await self._discover_lldp(device)
        neighbors.extend(lldp_neighbors)
        
        # Try CDP (Cisco-specific)
        cdp_neighbors = await self._discover_cdp(device)
        neighbors.extend(cdp_neighbors)
        
        return neighbors
    
    async def _discover_lldp(self, device: Dict) -> List[Dict]:
        """Discover LLDP neighbors"""
        neighbors = []
        
        try:
            from netmiko import ConnectHandler
            
            credentials = device.get('credentials', {})
            vendor = device.get('vendor', 'cisco_ios').lower()
            
            device_type_map = {
                'cisco': 'cisco_ios',
                'juniper': 'juniper_junos',
                'arista': 'arista_eos',
            }
            device_type = device_type_map.get(vendor, 'cisco_ios')
            
            conn = {
                'device_type': device_type,
                'host': device['management_ip'],
                'username': credentials.get('username'),
                'password': credentials.get('password'),
                'secret': credentials.get('enable_password', ''),
                'timeout': self.config.SSH_TIMEOUT,
            }
            
            netmiko_conn = ConnectHandler(**conn)
            if conn['secret']:
                netmiko_conn.enable()
            
            # Try different LLDP commands based on vendor
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
            
            netmiko_conn.disconnect()
            
        except ImportError:
            logger.warning("netmiko not available for LLDP discovery")
        except Exception as e:
            logger.error(f"LLDP discovery failed: {e}")
        
        return neighbors
    
    async def _discover_cdp(self, device: Dict) -> List[Dict]:
        """Discover CDP neighbors (Cisco)"""
        neighbors = []
        
        try:
            from netmiko import ConnectHandler
            
            credentials = device.get('credentials', {})
            vendor = device.get('vendor', 'cisco_ios').lower()
            
            # CDP is primarily Cisco
            if 'cisco' not in vendor and 'ios' not in vendor:
                return []
            
            device_type = 'cisco_ios'
            
            conn = {
                'device_type': device_type,
                'host': device['management_ip'],
                'username': credentials.get('username'),
                'password': credentials.get('password'),
                'secret': credentials.get('enable_password', ''),
                'timeout': self.config.SSH_TIMEOUT,
            }
            
            netmiko_conn = ConnectHandler(**conn)
            if conn['secret']:
                netmiko_conn.enable()
            
            # CDP commands
            cdp_commands = [
                "show cdp neighbors detail",
                "show cdp neighbors",
            ]
            
            for cmd in cdp_commands:
                try:
                    output = netmiko_conn.send_command(cmd, timeout=10)
                    if output and "CDP" in output:
                        parsed = self._parse_cdp_output(output)
                        for n in parsed:
                            n['protocol'] = 'cdp'
                        neighbors.extend(parsed)
                        break
                except Exception as e:
                    logger.debug(f"CDP command '{cmd}' failed: {e}")
                    continue
            
            netmiko_conn.disconnect()
            
        except ImportError:
            logger.warning("netmiko not available for CDP discovery")
        except Exception as e:
            logger.error(f"CDP discovery failed: {e}")
        
        return neighbors
    
    def _parse_lldp_output(self, output: str) -> List[Dict]:
        """Parse LLDP neighbor output"""
        neighbors = []
        
        # Simple parsing - split by device ID
        # In production, use TextFSM or similar
        lines = output.strip().split('\n')
        
        current_neighbor = {}
        for line in lines:
            line = line.strip()
            
            if 'Chassis ID:' in line:
                if current_neighbor:
                    neighbors.append(current_neighbor)
                current_neighbor = {
                    'chassis_id': line.split('Chassis ID:')[-1].strip(),
                }
            elif 'System Name:' in line:
                current_neighbor['hostname'] = line.split('System Name:')[-1].strip()
            elif 'Port ID:' in line:
                current_neighbor['local_port'] = line.split('Port ID:')[-1].strip()
            elif 'Management Address:' in line:
                current_neighbor['management_ip'] = line.split('Management Address:')[-1].strip()
            elif 'System Description:' in line:
                current_neighbor['description'] = line.split('System Description:')[-1].strip()[:200]
        
        if current_neighbor:
            neighbors.append(current_neighbor)
        
        return neighbors
    
    def _parse_cdp_output(self, output: str) -> List[Dict]:
        """Parse CDP neighbor output"""
        neighbors = []
        
        lines = output.strip().split('\n')
        
        current_neighbor = {}
        for line in lines:
            line = line.strip()
            
            if 'Device ID:' in line:
                if current_neighbor:
                    neighbors.append(current_neighbor)
                current_neighbor = {
                    'device_id': line.split('Device ID:')[-1].strip(),
                }
            elif 'IP Address:' in line:
                current_neighbor['management_ip'] = line.split('IP Address:')[-1].strip()
            elif 'Interface:' in line:
                current_neighbor['local_interface'] = line.split('Interface:')[-1].strip().split(',')[0]
            elif 'Port ID:' in line:
                current_neighbor['port_id'] = line.split('Port ID:')[-1].strip()
            elif 'Platform:' in line:
                current_neighbor['platform'] = line.split('Platform:')[-1].strip()
        
        if current_neighbor:
            neighbors.append(current_neighbor)
        
        return neighbors
    
    async def build_topology_graph(self, devices: List[Dict], all_neighbors: List[Dict]) -> Dict:
        """Build topology graph for Neo4j"""
        
        nodes = []
        edges = []
        
        # Add devices as nodes
        for device in devices:
            nodes.append({
                'id': device.get('management_ip'),
                'label': 'Device',
                'hostname': device.get('hostname'),
                'vendor': device.get('vendor'),
                'device_type': device.get('device_type'),
            })
        
        # Add neighbors and connections
        seen_edges = set()
        for neighbor in all_neighbors:
            # Add neighbor as node if not already present
            neighbor_ip = neighbor.get('management_ip')
            if neighbor_ip and neighbor_ip not in [n['id'] for n in nodes]:
                nodes.append({
                    'id': neighbor_ip,
                    'label': 'Device',
                    'hostname': neighbor.get('hostname'),
                    'discovered_via': neighbor.get('protocol'),
                })
            
            # Add edge
            # Note: Need to track which device discovered this neighbor
            # This would need to be passed in the neighbor data
        
        return {
            'nodes': nodes,
            'edges': edges,
        }


class NetFlowCollector:
    """Collect NetFlow/sFlow data for traffic analysis"""
    
    def __init__(self, config):
        self.config = config
        self.flow_cache = {}
    
    async def start_collector(self, port: int = 9995):
        """Start NetFlow/sFlow collector"""
        logger.info(f"Starting NetFlow collector on port {port}")
        # Note: This would require a separate process or thread
        # For now, just placeholder
        pass
    
    async def parse_flow_record(self, data: bytes) -> Dict:
        """Parse a single flow record"""
        # NetFlow v5 header structure (24 bytes)
        # Version (2), Count (2), SysUptime (4), Unix Secs (4), Unix NSecs (4), Flow Sequence (4)
        
        # This is a placeholder - actual implementation would parse
        # the binary NetFlow/sFlow data
        return {}
    
    def get_top_talkers(self, time_window: int = 3600) -> List[Dict]:
        """Get top talkers by traffic volume"""
        # Placeholder
        return []
    
    def get_traffic_matrix(self) -> Dict:
        """Get source-destination traffic matrix"""
        # Placeholder
        return {}


class ARPScanner:
    """ARP-based discovery for local networks"""
    
    def __init__(self, config):
        self.config = config
    
    async def scan_subnet(self, subnet: str) -> List[Dict]:
        """Scan subnet using ARP"""
        import subprocess
        
        logger.info(f"ARP scanning {subnet}")
        
        # Use nmap for ARP scan
        cmd = [
            "nmap",
            "-sn",              # Ping scan
            "-PR",              # ARP ping
            "-oX", "-",
            subnet
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return self._parse_arp_results(result.stdout)
            return []
            
        except Exception as e:
            logger.error(f"ARP scan failed: {e}")
            return []
    
    def _parse_arp_results(self, xml_output: str) -> List[Dict]:
        """Parse nmap ARP results"""
        import xml.etree.ElementTree as ET
        
        results = []
        
        try:
            root = ET.fromstring(xml_output)
            
            for host in root.findall(".//host"):
                status = host.find("status")
                if status is None or status.get("state") != "up":
                    continue
                
                host_data = {"source": "arp"}
                
                # Get addresses
                for addr in host.findall("address"):
                    addr_type = addr.get("addrtype")
                    if addr_type == "ipv4":
                        host_data["ip"] = addr.get("addr")
                    elif addr_type == "mac":
                        host_data["mac"] = addr.get("addr")
                        host_data["vendor"] = addr.get("vendor", "")
                
                # Hostnames
                hostnames = host.find("hostnames")
                if hostnames is not None:
                    hostname = hostnames.find("hostname")
                    if hostname is not None:
                        host_data["hostname"] = hostname.get("name")
                
                results.append(host_data)
        
        except ET.ParseError:
            pass
        
        return results


class ArpScanIntegration:
    """Integrate with arp-scan for Layer 2 discovery"""
    
    def __init__(self, config):
        self.config = config
    
    async def scan_interfaces(self) -> List[str]:
        """List available network interfaces"""
        try:
            result = subprocess.run(
                ["arp-scan", "--interface=en0", "--localnet"],
                capture_output=True,
                text=True,
                timeout=5
            )
            # Just check if arp-scan is available
            if result.returncode == 0 or "arp-scan" in result.stderr.lower():
                return await self._list_interfaces()
        except FileNotFoundError:
            logger.warning("arp-scan not installed - using nmap fallback")
        except Exception as e:
            logger.debug(f"arp-scan check: {e}")
        
        return []
    
    async def _list_interfaces(self) -> List[str]:
        """List available interfaces via arp-scan"""
        try:
            result = subprocess.run(
                ["arp-scan", "--list-interfaces"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                interfaces = []
                for line in result.stdout.split('\n'):
                    if line.strip() and not line.startswith('#'):
                        parts = line.split()[0] if line.split() else None
                        if parts and parts not in ['Interface', '']:
                            interfaces.append(parts)
                return interfaces
        except Exception as e:
            logger.error(f"Failed to list interfaces: {e}")
        return []
    
    async def scan_subnet(self, interface: str, subnet: str = None) -> List[Dict]:
        """Scan subnet using arp-scan"""
        cmd = ["arp-scan", "-I", interface]
        
        if subnet:
            cmd.append(subnet)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return self._parse_arp_scan(result.stdout)
            return []
            
        except FileNotFoundError:
            logger.warning("arp-scan not installed")
            return []
        except Exception as e:
            logger.error(f"arp-scan failed: {e}")
            return []
    
    def _parse_arp_scan(self, output: str) -> List[Dict]:
        """Parse arp-scan output"""
        results = []
        
        for line in output.split('\n'):
            # Skip headers and empty lines
            if not line.strip() or line.startswith('Interface') or line.startswith('Starting'):
                continue
            
            parts = line.split()
            if len(parts) >= 3:
                try:
                    # Typical format: IP Address    MAC Address    Vendor
                    results.append({
                        "source": "arp-scan",
                        "ip": parts[0],
                        "mac": parts[1],
                        "vendor": " ".join(parts[2:]) if len(parts) > 2 else "",
                    })
                except (IndexError, ValueError):
                    continue
        
        return results


class SwitchMapperIntegration:
    """Integrate with switch-mapper for recursive LLDP/SNMP topology mapping"""
    
    def __init__(self, config):
        self.config = config
    
    async def discover_topology(self, device: Dict) -> Dict:
        """Discover full network topology using LLDP/SNMP"""
        logger.info(f"Running switch-mapper on {device.get('hostname')}")
        
        # switch-mapper uses SNMP to walk LLDP MIBs
        # For now, we'll implement similar logic using netmiko + SNMP
        
        topology = {
            "nodes": [],
            "edges": [],
            "discovery_method": "lldp_snmp_walk"
        }
        
        # Get the device's LLDP neighbors
        from netmiko import ConnectHandler
        
        credentials = device.get('credentials', {})
        vendor = device.get('vendor', 'cisco_ios').lower()
        
        device_type_map = {
            'cisco': 'cisco_ios',
            'juniper': 'juniper_junos',
            'arista': 'arista_eos',
        }
        device_type = device_type_map.get(vendor, 'cisco_ios')
        
        try:
            conn = {
                'device_type': device_type,
                'host': device['management_ip'],
                'username': credentials.get('username'),
                'password': credentials.get('password'),
                'secret': credentials.get('enable_password', ''),
                'timeout': self.config.SSH_TIMEOUT,
            }
            
            netmiko_conn = ConnectHandler(**conn)
            if conn['secret']:
                netmiko_conn.enable()
            
            # Get LLDP neighbors detail
            output = netmiko_conn.send_command("show lldp neighbors detail", timeout=30)
            neighbors = self._parse_lldp_detail(output)
            
            # Add source device
            topology["nodes"].append({
                "id": device.get('management_ip'),
                "hostname": device.get('hostname'),
                "vendor": vendor,
                "type": "switch"
            })
            
            # Add edges to neighbors
            for neighbor in neighbors:
                neighbor_ip = neighbor.get('management_ip', neighbor.get('chassis_id', ''))
                
                topology["nodes"].append({
                    "id": neighbor_ip,
                    "hostname": neighbor.get('hostname'),
                    "vendor": neighbor.get('description', ''),
                    "type": "discovered"
                })
                
                topology["edges"].append({
                    "source": device.get('management_ip'),
                    "target": neighbor_ip,
                    "local_port": neighbor.get('local_port'),
                    "remote_port": neighbor.get('port_id'),
                    "protocol": "lldp"
                })
            
            # Recursively discover neighbors (simple version - depth=1)
            # In production, you'd traverse the full topology
            
            netmiko_conn.disconnect()
            
        except Exception as e:
            logger.error(f"Switch-mapper topology discovery failed: {e}")
        
        return topology
    
    def _parse_lldp_detail(self, output: str) -> List[Dict]:
        """Parse detailed LLDP output"""
        neighbors = []
        
        current = {}
        for line in output.split('\n'):
            line = line.strip()
            
            if 'Chassis ID:' in line:
                if current:
                    neighbors.append(current)
                current = {'chassis_id': line.split('Chassis ID:')[-1].strip()}
            elif 'System Name:' in line:
                current['hostname'] = line.split('System Name:')[-1].strip()
            elif 'Port ID:' in line:
                current['port_id'] = line.split('Port ID:')[-1].strip()
            elif 'Local Port Intf:' in line:
                current['local_port'] = line.split('Local Port Intf:')[-1].strip()
            elif 'Management Address:' in line:
                current['management_ip'] = line.split('Management Address:')[-1].strip()
            elif 'System Description:' in line:
                current['description'] = line.split('System Description:')[-1].strip()[:200]
        
        if current:
            neighbors.append(current)
        
        return neighbors


class FprobeIntegration:
    """Integrate with fprobe for NetFlow/sFlow collection"""
    
    def __init__(self, config):
        self.config = config
        self.flow_cache = {}
    
    async def start_collector(self, interface: str = "eth0", 
                             netflow_port: int = 9995,
                             sflow_port: int = 9996) -> Dict:
        """Start fprobe for flow collection"""
        logger.info(f"Starting fprobe on {interface} (NetFlow:{netflow_port}, sFlow:{sflow_port})")
        
        # fprobe command:
        # fprobe -i <interface> -fex <netflow_port> <collector_ip>
        
        return {
            "status": "configured",
            "interface": interface,
            "netflow_port": netflow_port,
            "sflow_port": sflow_port,
            "command": f"fprobe -i {interface} -fex {netflow_port} <collector_ip>"
        }
    
    async def parse_flow_file(self, filepath: str) -> List[Dict]:
        """Parse flow data from nfdump output"""
        flows = []
        
        try:
            # Use nfdump to read NetFlow data
            result = subprocess.run(
                ["nfdump", "-r", filepath, "-q", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if line.strip():
                        try:
                            flows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        
        except FileNotFoundError:
            logger.warning("nfdump not installed - cannot parse flow files")
        except Exception as e:
            logger.error(f"Flow parsing failed: {e}")
        
        return flows
    
    def get_top_talkers(self, time_window: int = 3600) -> List[Dict]:
        """Get top talkers using nfdump"""
        try:
            result = subprocess.run(
                ["nfdump", "-r", "/var/cache/flows/nfcapd.latest", 
                 "-s", "srcip", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                # Parse nfdump output
                return self._parse_top_talkers(result.stdout)
        
        except FileNotFoundError:
            logger.warning("nfdump not installed")
        except Exception as e:
            logger.error(f"Top talkers query failed: {e}")
        
        return []
    
    def _parse_top_talkers(self, output: str) -> List[Dict]:
        """Parse nfdump top talkers output"""
        talkers = []
        
        for line in output.split('\n'):
            if not line.strip() or not any(c.isdigit() for c in line):
                continue
            
            parts = line.split()
            if len(parts) >= 2:
                try:
                    talkers.append({
                        "ip": parts[0],
                        "flows": int(parts[1]) if parts[1].isdigit() else 0
                    })
                except (IndexError, ValueError):
                    continue
        
        return talkers[:10]
    
    def get_traffic_matrix(self) -> Dict:
        """Get source-destination traffic matrix"""
        matrix = {"nodes": [], "edges": []}
        
        try:
            # Get flows with src/dst
            result = subprocess.run(
                ["nfdump", "-r", "/var/cache/flows/nfcapd.latest",
                 "-o", "fmt:%sa %da %byt", "-q"],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                traffic = {}
                for line in result.stdout.split('\n'):
                    parts = line.split()
                    if len(parts) >= 3:
                        src, dst, bytes_ = parts[0], parts[1], int(parts[2])
                        
                        key = f"{src}->{dst}"
                        traffic[key] = traffic.get(key, 0) + bytes_
                
                # Convert to matrix format
                for key, bytes_ in traffic.items():
                    src, dst = key.split('->')
                    matrix["edges"].append({
                        "source": src,
                        "target": dst,
                        "bytes": bytes_
                    })
        
        except Exception as e:
            logger.error(f"Traffic matrix failed: {e}")
        
        return matrix


class NetdotIntegration:
    """Integrate with Netdot for network documentation"""
    
    def __init__(self, config):
        self.config = config
        self.base_url = config.NETDOT_URL if hasattr(config, 'NETDOT_URL') else None
        self.api_key = config.NETDOT_API_KEY if hasattr(config, 'NETDOT_API_KEY') else None
    
    async def sync_device(self, device: Dict) -> bool:
        """Sync device to Netdot"""
        if not self.base_url or not self.api_key:
            logger.warning("Netdot not configured")
            return False
        
        import httpx
        
        url = f"{self.base_url}/api/device"
        
        payload = {
            "name": device.get('hostname'),
            "ipaddress": device.get('management_ip'),
            "type": device.get('device_type', 'unknown'),
            "vendor": device.get('vendor', 'unknown'),
            "description": f"Discovered by NetDiscoverIT",
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    timeout=30
                )
                
                if response.status_code in [200, 201]:
                    logger.info(f"Synced device to Netdot: {device.get('hostname')}")
                    return True
                else:
                    logger.error(f"Netdot sync failed: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Netdot sync error: {e}")
        
        return False
    
    async def get_topology(self) -> Dict:
        """Get network topology from Netdot"""
        if not self.base_url or not self.api_key:
            return {}
        
        import httpx
        
        url = f"{self.base_url}/api/topology"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=30
                )
                
                if response.status_code == 200:
                    return response.json()
        
        except Exception as e:
            logger.error(f"Netdot topology fetch error: {e}")
        
        return {}
    
    async def get_device_list(self) -> List[Dict]:
        """Get all devices from Netdot"""
        if not self.base_url or not self.api_key:
            return []
        
        import httpx
        
        url = f"{self.base_url}/api/device"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=30
                )
                
                if response.status_code == 200:
                    return response.json()
        
        except Exception as e:
            logger.error(f"Netdot device list error: {e}")
        
        return []
