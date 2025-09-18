"""
Core engine: Chains modules via plugins for discovery workflow.
Extensible: Add AI hooks here later.
"""

from typing import Dict, Any, List
import asyncio
from pluggy import PluginManager as _PluginManager
from pydantic import BaseModel

class ScanResult(BaseModel):
    devices: List[Dict[str, Any]]
    metadata: Dict[str, Any]

class DiscoveryEngine:
    def __init__(self):
        self.pm = _PluginManager("netdiscoverit")
        self.pm.add_hookspecs_from_spec_name("netdiscoverit.hooks")  # Define hooks in hooks.py later
    
    def load_plugins(self):
        # Register built-in modules as plugins
        from .plugins import load_builtins
        load_builtins(self.pm)
    
    async def run_discovery(self, target: str, verbose: bool = False) -> ScanResult:
        """Full pipeline: Scan → Identify → Categorize."""
        # Async scan stub
        scan_data = await self._scan(target, verbose)
        identified = self._identify(scan_data)
        categorized = self._categorize(identified)
        return ScanResult(devices=categorized, metadata={"target": target})
    
    async def _scan(self, target: str, verbose: bool) -> Dict:
        # Delegate to scanner plugin
        results = self.pm.hook.scan_network(target=target, verbose=verbose)
        return {"raw_devices": results}
    
    def _identify(self, data: Dict) -> List[Dict]:
        # Delegate to identifier
        return self.pm.hook.identify_devices(devices=data["raw_devices"])
    
    def _categorize(self, devices: List[Dict]) -> List[Dict]:
        # Delegate to categorizer
        return self.pm.hook.categorize_devices(devices=devices)
    
    def generate_documentation(self, scan_file: str, template: str) -> Dict:
        # Load data, apply template via documenter
        import yaml
        with open(scan_file) as f:
            data = yaml.safe_load(f)
        docs = self.pm.hook.generate_docs(data=data, template=template)
        return docs  # Returns dict for PDF rendering