"""
IVRE Integration Module
Network recon framework - self-hosted alternative to Shodan/ZoomEye
https://github.com/ivre/ivre
"""

import asyncio
import logging
import subprocess
import json
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class IVREIntegration:
    """
    Integrate with IVRE for comprehensive network reconnaissance.
    
    IVRE supports:
    - Passive: Zeek, Argus, Nfdump, p0f, airodump-ng
    - Active: Nmap, Masscan, ZGrab2, ZDNS, Nuclei, httpx, dnsx, tlsx
    """
    
    def __init__(self, config):
        self.config = config
        self.db_type = config.IVRE_DB_TYPE if hasattr(config, 'IVRE_DB_TYPE') else 'mongodb'
    
    async def scan_nmap(self, target: str, scan_type: str = "quick") -> Dict:
        """
        Run Nmap scan via IVRE
        
        scan_type: "quick", "full", "stealth", "service", "vuln"
        """
        logger.info(f"Running IVRE Nmap scan on {target} ({scan_type})")
        
        # IVRE uses different scan profiles
        scan_options = {
            "quick": "-F",  # Top 100 ports
            "full": "-p-",  # All ports
            "stealth": "-sS -T2",  # SYN scan, slow
            "service": "-sV",  # Service version detection
            "vuln": "-sV --script vuln",  # Vulnerability scripts
        }
        
        options = scan_options.get(scan_type, "-F")
        
        cmd = [
            "ivre", "nmap", 
            "--",  # Pass through to nmap
            target
        ] + options.split()
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                # Parse IVRE output (usually JSON)
                return self._parse_ivre_output(result.stdout)
            else:
                logger.error(f"IVRE scan failed: {result.stderr}")
                return {}
                
        except FileNotFoundError:
            logger.warning("IVRE not installed - falling back to direct nmap")
            return await self._fallback_nmap(target, scan_type)
        except Exception as e:
            logger.error(f"IVRE scan error: {e}")
            return {}
    
    async def _fallback_nmap(self, target: str, scan_type: str = "quick") -> Dict:
        """Fallback to direct nmap if IVRE not available"""
        logger.info(f"Running fallback Nmap scan on {target}")
        
        scan_options = {
            "quick": "-F",
            "full": "-p-",
            "stealth": "-sS -T2",
            "service": "-sV",
            "vuln": "-sV --script vuln",
        }
        
        options = scan_options.get(scan_type, "-F")
        
        cmd = ["nmap"] + options.split() + ["-oX", "-", target]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                # Parse XML
                return self._parse_nmap_xml(result.stdout)
            return {}
            
        except Exception as e:
            logger.error(f"Fallback nmap failed: {e}")
            return {}
    
    async def scan_masscan(self, target: str, rate: int = 10000) -> Dict:
        """Run Masscan via IVRE"""
        logger.info(f"Running IVRE Masscan on {target} (rate={rate})")
        
        cmd = [
            "ivre", "masscan",
            "--rate", str(rate),
            "-p1-1000",  # Quick port range
            "--", target
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                return self._parse_ivre_output(result.stdout)
            return {}
                
        except FileNotFoundError:
            logger.warning("IVRE not installed")
            return await self._fallback_masscan(target, rate)
        except Exception as e:
            logger.error(f"Masscan error: {e}")
            return {}
    
    async def _fallback_masscan(self, target: str, rate: int = 10000) -> Dict:
        """Fallback to direct masscan"""
        cmd = [
            "masscan",
            "--rate", str(rate),
            "-oJ", "-",
            "-p1-1000",
            target
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600
            )
            
            if result.returncode == 0:
                return self._parse_masscan_json(result.stdout)
            return {}
            
        except Exception as e:
            logger.error(f"Fallback masscan failed: {e}")
            return {}
    
    async def passive_discovery(self, interface: str = None) -> Dict:
        """
        Run passive discovery using Zeek/p0f
        Requires IVRE with passive sensors configured
        """
        logger.info("Running IVRE passive discovery")
        
        cmd = ["ivre", "passive"]
        
        if interface:
            cmd.extend(["-i", interface])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            if result.returncode == 0:
                return self._parse_ivre_output(result.stdout)
            return {}
            
        except FileNotFoundError:
            logger.warning("IVRE not installed - passive discovery unavailable")
            return {}
        except Exception as e:
            logger.error(f"Passive discovery error: {e}")
            return {}
    
    async def get_hosts(self, filters: Dict = None) -> List[Dict]:
        """Get hosts from IVRE database"""
        logger.info("Querying IVRE database for hosts")
        
        cmd = ["ivre", "view"]
        
        # Add filters if provided
        if filters:
            if 'country' in filters:
                cmd.extend(["--country", filters['country']])
            if 'source' in filters:
                cmd.extend(["--source", filters['source']])
            if 'port' in filters:
                cmd.extend(["--port", str(filters['port'])])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return self._parse_ivre_output(result.stdout)
            return []
            
        except FileNotFoundError:
            logger.warning("IVRE not installed")
            return []
        except Exception as e:
            logger.error(f"IVRE view error: {e}")
            return []
    
    async def get_services(self, host: str = None) -> List[Dict]:
        """Get services from IVRE database"""
        cmd = ["ivre", "view", "--services"]
        
        if host:
            cmd.append(host)
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return self._parse_ivre_output(result.stdout)
            return []
            
        except Exception as e:
            logger.error(f"IVRE services error: {e}")
            return []
    
    def _parse_ivre_output(self, output: str) -> Dict:
        """Parse IVRE output (usually JSON or CSV)"""
        # Try JSON first
        try:
            data = json.loads(output)
            return data if isinstance(data, dict) else {"results": data}
        except json.JSONDecodeError:
            pass
        
        # Try lines as JSON
        results = []
        for line in output.strip().split('\n'):
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    # Plain text - just return as-is
                    return {"raw": output}
        
        return {"results": results} if results else {"raw": output}
    
    def _parse_nmap_xml(self, xml_output: str) -> Dict:
        """Parse Nmap XML output"""
        import xml.etree.ElementTree as ET
        
        try:
            root = ET.fromstring(xml_output)
            hosts = []
            
            for host in root.findall(".//host"):
                host_data = {"ports": []}
                
                # Address
                for addr in host.findall("address"):
                    addr_type = addr.get("addrtype")
                    if addr_type == "ipv4":
                        host_data["addr"] = addr.get("addr")
                    elif addr_type == "mac":
                        host_data["mac"] = addr.get("addr")
                        host_data["mac_vendor"] = addr.get("vendor", "")
                
                # Hostnames
                hostnames = host.find("hostnames")
                if hostnames is not None:
                    host_data["hostnames"] = [
                        h.get("name") for h in hostnames.findall("hostname")
                    ]
                
                # Ports
                for port in host.findall(".//port"):
                    port_data = {
                        "portid": port.get("portid"),
                        "protocol": port.get("protocol"),
                    }
                    
                    state = port.find("state")
                    if state is not None:
                        port_data["state"] = state.get("state")
                    
                    service = port.find("service")
                    if service is not None:
                        port_data["service"] = {
                            "name": service.get("name"),
                            "product": service.get("product"),
                            "version": service.get("version"),
                        }
                    
                    host_data["ports"].append(port_data)
                
                hosts.append(host_data)
            
            return {"hosts": hosts}
            
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            return {}
    
    def _parse_masscan_json(self, json_output: str) -> Dict:
        """Parse Masscan JSON output"""
        try:
            data = json.loads(json_output)
            return {"hosts": data} if isinstance(data, list) else data
        except json.JSONDecodeError:
            return {}
    
    async def export_for_neo4j(self, scan_results: Dict) -> Dict:
        """Export IVRE results for Neo4j graph"""
        
        nodes = []
        edges = []
        
        hosts = scan_results.get("hosts", [])
        
        for host in hosts:
            node = {
                "id": host.get("addr", host.get("ip")),
                "label": "Host",
                "hostnames": host.get("hostnames", []),
                "mac_vendor": host.get("mac_vendor"),
            }
            
            # Add ports as properties
            ports = host.get("ports", [])
            open_ports = [p for p in ports if p.get("state") == "open"]
            node["port_count"] = len(open_ports)
            node["services"] = [
                p.get("service", {}).get("name", "unknown") 
                for p in open_ports
            ]
            
            nodes.append(node)
        
        return {
            "nodes": nodes,
            "edges": edges,
            "source": "ivre"
        }


class IVREDBManager:
    """Manage IVRE database connections"""
    
    def __init__(self, config):
        self.config = config
        self.db_type = config.IVRE_DB_TYPE if hasattr(config, 'IVRE_DB_TYPE') else 'mongodb'
        self.db_url = config.IVRE_DB_URL if hasattr(config, 'IVRE_DB_URL') else None
    
    async def init_db(self) -> bool:
        """Initialize IVRE database"""
        logger.info(f"Initializing IVRE database ({self.db_type})")
        
        cmd = ["ivre", "db-init"]
        
        if self.db_type == "mongodb":
            # Default
            pass
        elif self.db_type == "postgresql":
            cmd.extend(["--postgresql"])
        elif self.db_type == "elasticsearch":
            cmd.extend(["--elastic"])
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            return result.returncode == 0
            
        except FileNotFoundError:
            logger.warning("IVRE not installed")
            return False
        except Exception as e:
            logger.error(f"DB init error: {e}")
            return False
    
    async def import_nmap_result(self, xml_file: str) -> bool:
        """Import Nmap XML result to IVRE"""
        cmd = ["ivre", "nmap2db", "-r", xml_file]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )
            
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"Import error: {e}")
            return False
    
    async def import_pcap(self, pcap_file: str) -> bool:
        """Import PCAP file via Zeek"""
        cmd = ["ivre", "pcap2db", "-r", pcap_file]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            return result.returncode == 0
            
        except Exception as e:
            logger.error(f"PCAP import error: {e}")
            return False
    
    async def get_scan_count(self) -> int:
        """Get total scan count"""
        cmd = ["ivre", "db-count"]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                return int(result.stdout.strip())
            
        except Exception:
            pass
        
        return 0
