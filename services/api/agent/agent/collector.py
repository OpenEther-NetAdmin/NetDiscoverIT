"""
Device Collector
Discovers and collects data from network devices
"""

import asyncio
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class DeviceCollector:
    """Collects device information via SSH, SNMP, etc."""
    
    def __init__(self, config):
        self.config = config
        self.ssh_connections = {}
    
    async def discover_devices(self) -> List[Dict]:
        """Discover devices on the network"""
        devices = []
        
        # Load devices from config
        for device_config in self.config.devices:
            device = {
                'hostname': device_config.get('hostname'),
                'management_ip': device_config.get('ip'),
                'device_type': device_config.get('type', 'unknown'),
                'vendor': device_config.get('vendor', 'unknown'),
                'credentials': device_config.get('credentials', {}),
                'methods': device_config.get('methods', ['ssh']),
            }
            devices.append(device)
        
        # Also try Nmap auto-discovery if configured
        network_ranges = self.config.devices[0].get('scan_ranges', []) if self.config.devices else []
        if network_ranges:
            nmap_devices = await self._discover_with_nmap(network_ranges)
            for nmap_device in nmap_devices:
                if not any(d.get('management_ip') == nmap_device.get('management_ip') for d in devices):
                    devices.append(nmap_device)
        
        return devices
    
    async def _discover_with_nmap(self, network_ranges: List[str]) -> List[Dict]:
        """Discover devices using Nmap"""
        discovered = []
        
        try:
            import nmap
            
            nm = nmap.PortScanner()
            
            for network in network_ranges:
                logger.info(f"Scanning network: {network}")
                
                nm.scan(
                    hosts=network,
                    ports='22,23,80,443,161',
                    arguments='-sn -PR'
                )
                
                for host in nm.all_hosts():
                    host_info = {
                        'management_ip': host,
                        'hostname': nm[host].hostname() or host,
                        'device_type': 'unknown',
                        'vendor': 'unknown',
                        'methods': ['ssh'],
                    }
                    
                    if 'mac' in nm[host]:
                        host_info['mac_address'] = nm[host]['mac']
                        vendor = nm[host].get('vendor', {}).get(nm[host]['mac'])
                        if vendor:
                            host_info['vendor'] = vendor
                    
                    if 'osmatch' in nm[host] and nm[host]['osmatch']:
                        os_match = nm[host]['osmatch'][0]
                        host_info['os_type'] = os_match.get('osclass', {}).get('type', 'unknown')
                    
                    discovered.append(host_info)
                    logger.info(f"Discovered: {host_info['hostname']} ({host_info['management_ip']})")
                    
        except ImportError:
            logger.warning("Nmap Python library not installed. Run: pip install python3-nmap")
        except Exception as e:
            logger.error(f"Nmap discovery failed: {e}")
        
        return discovered
    
    async def get_config(self, device: Dict) -> str:
        """Get running configuration from device"""
        method = device.get('methods', ['ssh'])[0]
        
        if method == 'ssh':
            return await self._get_config_ssh(device)
        elif method == 'snmp':
            return await self._get_config_snmp(device)
        else:
            raise ValueError(f"Unsupported discovery method: {method}")
    
    async def _get_config_ssh(self, device: Dict) -> str:
        """Get config via SSH using Netmiko"""
        try:
            from netmiko import ConnectHandler
            
            credentials = device.get('credentials', {})
            
            # Determine device type for Netmiko
            vendor = device.get('vendor', 'cisco_ios').lower()
            device_type_map = {
                'cisco': 'cisco_ios',
                'juniper': 'juniper_junos',
                'arista': 'arista_eos',
                'f5': 'f5_ltm',
                'palo alto': 'paloalto_panos',
            }
            
            device_type = device_type_map.get(vendor, 'cisco_ios')
            
            # Build connection dict
            conn = {
                'device_type': device_type,
                'host': device['management_ip'],
                'username': credentials.get('username'),
                'password': credentials.get('password'),
                'secret': credentials.get('enable_password', ''),
                'timeout': self.config.SSH_TIMEOUT,
            }
            
            logger.info(f"Connecting to {device['hostname']} ({device['management_ip']})")
            
            # Connect and get config
            netmiko_conn = ConnectHandler(**conn)
            
            # Enter enable mode if needed
            if conn['secret']:
                netmiko_conn.enable()
            
            # Get running config
            output = netmiko_conn.send_command("show running-config")
            
            # Also get additional info
            show_version = netmiko_conn.send_command("show version")
            show_interface = netmiko_conn.send_command("show ip interface brief")
            show_vlan = netmiko_conn.send_command("show vlan")
            
            # Combine all outputs
            full_config = f"=== SHOW RUNNING-CONFIG ===\n{output}\n\n"
            full_config += f"=== SHOW VERSION ===\n{show_version}\n\n"
            full_config += f"=== SHOW IP INTERFACE BRIEF ===\n{show_interface}\n\n"
            full_config += f"=== SHOW VLAN ===\n{show_vlan}"
            
            netmiko_conn.disconnect()
            
            return full_config
            
        except Exception as e:
            logger.error(f"SSH config retrieval failed for {device['hostname']}: {e}")
            raise
    
    async def _get_config_snmp(self, device: Dict) -> str:
        """Get config via SNMP"""
        try:
            from easysnmp import Session
            
            credentials = device.get('credentials', {})
            community = credentials.get('snmp_community', 'public')
            
            logger.info(f"SNMP polling {device['hostname']} ({device['management_ip']})")
            
            session = Session(
                hostname=device['management_ip'],
                community=community,
                version=2
            )
            
            # Get system info
            sys_descr = session.get('sysDescr.0')
            sys_name = session.get('sysName.0')
            sys_uptime = session.get('sysUpTime.0')
            
            # Get interface info
            interfaces = session.walk('ifDescr')
            
            config = f"=== SNMP DATA ===\n"
            config += f"System Description: {sys_descr.value}\n"
            config += f"System Name: {sys_name.value}\n"
            config += f"System Uptime: {sys_uptime.value}\n"
            config += f"\nInterfaces:\n"
            for iface in interfaces:
                config += f"  {iface.oid}: {iface.value}\n"
            
            return config
            
        except Exception as e:
            logger.error(f"SNMP retrieval failed for {device['hostname']}: {e}")
            raise
    
    async def get_interfaces(self, device: Dict) -> List[Dict]:
        """Get interface details"""
        method = device.get('methods', ['ssh'])[0]
        
        if method == 'ssh':
            return await self._get_interfaces_ssh(device)
        elif method == 'snmp':
            return await self._get_interfaces_snmp(device)
        return []
    
    async def get_vlans(self, device: Dict) -> List[Dict]:
        """Get VLAN information"""
        method = device.get('methods', ['ssh'])[0]
        
        if method == 'ssh':
            return await self._get_vlans_ssh(device)
        elif method == 'snmp':
            return await self._get_vlans_snmp(device)
        return []
    
    async def get_routing_table(self, device: Dict) -> List[Dict]:
        """Get routing table"""
        method = device.get('methods', ['ssh'])[0]
        
        if method == 'ssh':
            return await self._get_routing_ssh(device)
        elif method == 'snmp':
            return await self._get_routing_snmp(device)
        return []
    
    async def _get_interfaces_ssh(self, device: Dict) -> List[Dict]:
        """Get interfaces via SSH"""
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
            
            output = netmiko_conn.send_command("show ip interface brief")
            lines = output.strip().split('\n')[1:]
            
            interfaces = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 4:
                    interfaces.append({
                        'name': parts[0],
                        'ip_address': parts[1] if parts[1] != 'unassigned' else None,
                        'status': parts[2],
                        'protocol': parts[3] if len(parts) > 3 else 'up',
                    })
            
            netmiko_conn.disconnect()
            return interfaces
            
        except Exception as e:
            logger.error(f"Failed to get interfaces via SSH: {e}")
            return []
    
    async def _get_interfaces_snmp(self, device: Dict) -> List[Dict]:
        """Get interfaces via SNMP"""
        try:
            from easysnmp import Session
            
            credentials = device.get('credentials', {})
            community = credentials.get('snmp_community', 'public')
            
            session = Session(
                hostname=device['management_ip'],
                community=community,
                version=2
            )
            
            interfaces = []
            for iface in session.walk('ifDescr'):
                interfaces.append({
                    'oid': iface.oid,
                    'name': iface.value,
                })
            
            return interfaces
            
        except Exception as e:
            logger.error(f"Failed to get interfaces via SNMP: {e}")
            return []
    
    async def _get_vlans_ssh(self, device: Dict) -> List[Dict]:
        """Get VLANs via SSH"""
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
            
            output = netmiko_conn.send_command("show vlan brief")
            lines = output.strip().split('\n')[2:]
            
            vlans = []
            for line in lines:
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        vlan_id = int(parts[0])
                        vlans.append({
                            'vlan_id': vlan_id,
                            'name': parts[1],
                        })
                    except ValueError:
                        continue
            
            netmiko_conn.disconnect()
            return vlans
            
        except Exception as e:
            logger.error(f"Failed to get VLANs via SSH: {e}")
            return []
    
    async def _get_vlans_snmp(self, device: Dict) -> List[Dict]:
        """Get VLANs via SNMP"""
        try:
            from easysnmp import Session
            
            credentials = device.get('credentials', {})
            community = credentials.get('snmp_community', 'public')
            
            session = Session(
                hostname=device['management_ip'],
                community=community,
                version=2
            )
            
            vlans = []
            for vlan in session.walk('vlan'):
                vlans.append({
                    'oid': vlan.oid,
                    'value': vlan.value,
                })
            
            return vlans
            
        except Exception as e:
            logger.error(f"Failed to get VLANs via SNMP: {e}")
            return []
    
    async def _get_routing_ssh(self, device: Dict) -> List[Dict]:
        """Get routing table via SSH"""
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
            
            output = netmiko_conn.send_command("show ip route")
            lines = output.strip().split('\n')
            
            routes = []
            for line in lines:
                if line.startswith('C') or line.startswith('S') or line.startswith('O') or line.startswith('D'):
                    parts = line.split()
                    if len(parts) >= 2:
                        routes.append({
                            'protocol': parts[0],
                            'network': parts[1],
                        })
            
            netmiko_conn.disconnect()
            return routes
            
        except Exception as e:
            logger.error(f"Failed to get routing table via SSH: {e}")
            return []
    
    async def _get_routing_snmp(self, device: Dict) -> List[Dict]:
        """Get routing table via SNMP"""
        try:
            from easysnmp import Session
            
            credentials = device.get('credentials', {})
            community = credentials.get('snmp_community', 'public')
            
            session = Session(
                hostname=device['management_ip'],
                community=community,
                version=2
            )
            
            routes = []
            for route in session.walk('ipRouteDest'):
                routes.append({
                    'destination': route.value,
                    'oid': route.oid,
                })
            
            return routes
            
        except Exception as e:
            logger.error(f"Failed to get routing table via SNMP: {e}")
            return []
    
    async def close(self):
        """Close all connections"""
        for conn in self.ssh_connections.values():
            conn.disconnect()
        self.ssh_connections = {}
