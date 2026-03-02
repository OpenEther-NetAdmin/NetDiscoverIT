"""
Topology Discovery Module
Discovers network topology using CDP, LLDP, and other protocols
"""

import asyncio
import logging
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
