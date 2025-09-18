"""
Identifier module: Queries devices for vendor/OS via SNMP, falls back to Nmap.
Focus: SMB gear (Cisco, HP, Windows). Extensible for enterprise.
"""

from typing import List, Dict
import nmap
from pysnmp.hlapi import getCmd, SnmpEngine, CommunityData, UdpTransportTarget, ContextData, ObjectType, ObjectIdentity

class IdentifierPlugin:
    def identify_devices(self, devices: List[Dict]) -> List[Dict]:
        """
        Enrich device data with vendor/OS/model via SNMP or Nmap.
        Input: [{"ip": "192.168.1.1", "mac": "...", ...}, ...]
        Output: Adds "vendor", "os", "model" keys.
        """
        identified = []
        for device in devices:
            enriched = device.copy()
            if device["state"] == "up":
                # Try SNMP first
                snmp_data = self._snmp_query(device["ip"])
                if snmp_data:
                    enriched.update(snmp_data)
                else:
                    # Fallback to Nmap OS detection
                    nmap_data = self._nmap_identify(device["ip"])
                    enriched.update(nmap_data)
            identified.append(enriched)
        return identified

    def _snmp_query(self, ip: str) -> Dict:
        """Query device via SNMP for system info."""
        try:
            iterator = getCmd(
                SnmpEngine(),
                CommunityData("public"),  # SMB default, configurable later
                UdpTransportTarget((ip, 161), timeout=1, retries=1),
                ContextData(),
                ObjectType(ObjectIdentity("1.3.6.1.2.1.1.1.0")),  # sysDescr
            )
            error_indication, error_status, error_index, var_binds = next(iterator)
            if error_indication or error_status:
                return {}
            sys_descr = str(var_binds[0][1])
            return {
                "vendor": self._parse_vendor(sys_descr),
                "os": self._parse_os(sys_descr),
                "model": self._parse_model(sys_descr),
            }
        except Exception:
            return {}

    def _nmap_identify(self, ip: str) -> Dict:
        """Fallback: Use Nmap for OS/vendor detection."""
        nm = nmap.PortScanner()
        nm.scan(ip, arguments="-O --osscan-guess")
        if ip in nm.all_hosts() and "osclass" in nm[ip]:
            osclass = nm[ip]["osclass"][0] if nm[ip]["osclass"] else {}
            return {
                "vendor": osclass.get("vendor", "unknown"),
                "os": osclass.get("osfamily", "unknown"),
                "model": osclass.get("osgen", "unknown"),
            }
        return {"vendor": "unknown", "os": "unknown", "model": "unknown"}

    def _parse_vendor(self, sys_descr: str) -> str:
        """Extract vendor from SNMP sysDescr."""
        for vendor in ["Cisco", "HP", "Microsoft", "Ubiquiti"]:
            if vendor.lower() in sys_descr.lower():
                return vendor
        return "unknown"

    def _parse_os(self, sys_descr: str) -> str:
        """Extract OS from SNMP sysDescr."""
        if "ios" in sys_descr.lower():
            return "Cisco IOS"
        if "windows" in sys_descr.lower():
            return "Windows"
        return "unknown"

    def _parse_model(self, sys_descr: str) -> str:
        """Extract model (basic heuristic)."""
        # Add regex for common SMB devices (e.g., Catalyst 2950)
        return "unknown"  # Stub: Enhance with patterns