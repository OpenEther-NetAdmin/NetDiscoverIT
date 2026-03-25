"""
Network Scanner
Enhanced discovery using nmap and masscan
"""

import asyncio
import logging
import json
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class NetworkScanner:
    """Network scanning using nmap and masscan"""
    
    def __init__(self, config):
        self.config = config
    
    async def scan_network(self, target: str, method: str = "nmap") -> List[Dict]:
        """Scan network using nmap or masscan"""
        if method == "nmap":
            return await self._scan_nmap(target)
        elif method == "masscan":
            return await self._scan_masscan(target)
        elif method == "both":
            # Run both and merge results
            nmap_results = await self._scan_nmap(target)
            masscan_results = await self._scan_masscan(target)
            return self._merge_results(nmap_results, masscan_results)
        else:
            raise ValueError(f"Unknown scan method: {method}")
    
    async def _scan_nmap(self, target: str) -> List[Dict]:
        """Run nmap scan"""
        import subprocess
        
        logger.info(f"Running nmap scan on {target}")
        
        # Nmap command with OS detection, service version, and script scan
        cmd = [
            "nmap",
            "-sn",              # Ping scan (disable port scan)
            "-PR",              # ARP ping
            "-oX", "-",        # XML output to stdout
            target
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode != 0:
                logger.warning(f"Nmap scan failed: {result.stderr}")
                return []
            
            # Parse XML output
            return self._parse_nmap_xml(result.stdout)
            
        except FileNotFoundError:
            logger.error("nmap not installed")
            return []
        except Exception as e:
            logger.error(f"Nmap scan error: {e}")
            return []
    
    async def _scan_masscan(self, target: str) -> List[Dict]:
        """Run masscan scan"""
        import subprocess
        
        logger.info(f"Running masscan scan on {target}")
        
        # Masscan command
        cmd = [
            "masscan",
            "-oJ", "-",        # JSON output to stdout
            "--rate", "10000",
            "-p1-1000",        # Quick port scan
            target
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode != 0:
                logger.warning(f"Masscan scan failed: {result.stderr}")
                return []
            
            # Parse JSON output
            return self._parse_masscan_json(result.stdout)
            
        except FileNotFoundError:
            logger.error("masscan not installed")
            return []
        except Exception as e:
            logger.error(f"Masscan scan error: {e}")
            return []
    
    def _parse_nmap_xml(self, xml_output: str) -> List[Dict]:
        """Parse nmap XML output"""
        import xml.etree.ElementTree as ET
        
        results = []
        
        try:
            root = ET.fromstring(xml_output)
            
            for host in root.findall(".//host"):
                host_data = {
                    "source": "nmap",
                    "status": "up"
                }
                
                # Status
                status = host.find("status")
                if status is not None:
                    host_data["status"] = status.get("state", "unknown")
                
                # Address
                address = host.find("address")
                if address is not None:
                    host_data["ip"] = address.get("addr")
                    host_data["mac"] = address.get("addr", "").replace(":", "-").upper()
                    host_data["vendor"] = address.get("vendor", "")
                
                # Hostnames
                hostnames = host.find("hostnames")
                if hostnames is not None:
                    hostname = hostnames.find("hostname")
                    if hostname is not None:
                        host_data["hostname"] = hostname.get("name")
                
                # OS Detection
                os = host.find("osmatch")
                if os is not None:
                    host_data["os"] = os.get("name", "")
                    host_data["os_accuracy"] = os.get("accuracy", "")
                
                # Ports
                ports = []
                for port in host.findall(".//port"):
                    port_data = {
                        "port": port.get("portid"),
                        "protocol": port.get("protocol"),
                        "state": port.find("state").get("state") if port.find("state") is not None else ""
                    }
                    
                    # Service
                    service = port.find("service")
                    if service is not None:
                        port_data["service"] = service.get("name")
                        port_data["product"] = service.get("product")
                        port_data["version"] = service.get("version")
                    
                    ports.append(port_data)
                
                if ports:
                    host_data["ports"] = ports
                
                results.append(host_data)
        
        except ET.ParseError as e:
            logger.error(f"Failed to parse nmap XML: {e}")
        
        return results
    
    def _parse_masscan_json(self, json_output: str) -> List[Dict]:
        """Parse masscan JSON output"""
        results = []
        
        try:
            data = json.loads(json_output)
            
            for scan_info in data:
                host_data = {
                    "source": "masscan",
                    "ip": scan_info.get("ip", ""),
                    "ports": []
                }
                
                # Parse ports
                for port_info in scan_info.get("ports", []):
                    host_data["ports"].append({
                        "port": port_info.get("port"),
                        "protocol": port_info.get("protocol"),
                        "state": port_info.get("state", {}).get("state"),
                        "service": port_info.get("service", {}).get("name")
                    })
                
                results.append(host_data)
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse masscan JSON: {e}")
        
        return results
    
    def _merge_results(self, nmap_results: List[Dict], masscan_results: List[Dict]) -> List[Dict]:
        """Merge results from multiple scanners"""
        merged = {}
        
        # Add nmap results
        for result in nmap_results:
            ip = result.get("ip")
            if ip:
                if ip not in merged:
                    merged[ip] = result
                else:
                    # Merge data
                    merged[ip].update(result)
        
        # Add masscan results
        for result in masscan_results:
            ip = result.get("ip")
            if ip:
                if ip not in merged:
                    merged[ip] = result
                else:
                    # Merge ports (masscan might have different/better port data)
                    existing_ports = {p["port"]: p for p in merged[ip].get("ports", [])}
                    for port in result.get("ports", []):
                        if port["port"] not in existing_ports:
                            existing_ports[port["port"]] = port
                    merged[ip]["ports"] = list(existing_ports.values())
        
        return list(merged.values())
    
    async def get_device_fingerprint(self, ip: str) -> Dict:
        """Get detailed fingerprint for a specific device"""
        import subprocess
        
        logger.info(f"Fingerprinting {ip}")
        
        cmd = [
            "nmap",
            "-O",              # OS detection
            "-sV",             # Service version
            "-sC",             # Default scripts
            "-oX", "-",
            ip
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode == 0:
                return self._parse_nmap_xml(result.stdout)[0]
            else:
                return {}
                
        except Exception as e:
            logger.error(f"Fingerprint error: {e}")
            return {}
    
    async def scan_top_ports(self, target: str, top_ports: int = 100) -> List[Dict]:
        """Quick scan of top ports"""
        import subprocess
        
        logger.info(f"Quick port scan on {target}")
        
        cmd = [
            "nmap",
            "-sT",             # TCP connect scan
            f"--top-ports", str(top_ports),
            "--open",          # Show only open ports
            "-oX", "-",
            target
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180
            )
            
            if result.returncode == 0:
                return self._parse_nmap_xml(result.stdout)
            else:
                return []
                
        except Exception as e:
            logger.error(f"Port scan error: {e}")
            return []
