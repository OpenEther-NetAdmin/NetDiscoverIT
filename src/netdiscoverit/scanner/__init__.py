"""
Scanner module: Uses Nmap for device discovery.
SMB/WiFi focus: Add -sV --script smb-os-discovery for SMBs.
"""

import nmap
from typing import List, Dict

class ScannerPlugin:
    def scan_network(self, target: str, verbose: bool = False) -> List[Dict]:
        nm = nmap.PortScanner()
        nm.scan(target, arguments="-sn -T4")  # Host discovery only for speed
        devices = []
        for host in nm.all_hosts():
            info = nm[host]
            device = {
                "ip": host,
                "hostname": info.hostname() if info.hostname() else "unknown",
                "mac": info.get("addresses", {}).get("mac", "unknown"),
                "state": info.state(),
            }
            if verbose:
                print(f"Discovered: {host} ({device['state']})")
            devices.append(device)
        return devices