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
        
        # TODO: Implement network scanning (Nmap) to auto-discover devices
        # For now, devices are configured manually
        
        return devices
    
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
        # TODO: Implement based on device type
        return []
    
    async def get_routing_table(self, device: Dict) -> List[Dict]:
        """Get routing table"""
        # TODO: Implement based on device type
        return []
    
    async def close(self):
        """Close all connections"""
        for conn in self.ssh_connections.values():
            conn.disconnect()
        self.ssh_connections = {}
