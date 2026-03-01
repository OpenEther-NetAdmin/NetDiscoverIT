"""
Device Vectorizer
Generates embeddings for ML analysis
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class DeviceVectorizer:
    """Generates vector embeddings for devices"""
    
    def __init__(self, config):
        self.config = config
    
    async def generate_vectors(self, device_metadata: Dict) -> Dict:
        """Generate vector embeddings for a device"""
        vectors = {}
        
        # Generate different vector types
        vectors['device_role'] = await self._generate_role_vector(device_metadata)
        vectors['topology'] = await self._generate_topology_vector(device_metadata)
        vectors['security'] = await self._generate_security_vector(device_metadata)
        
        return vectors
    
    async def _generate_role_vector(self, metadata: Dict) -> List[float]:
        """Generate device role vector"""
        # Use sentence-transformers if available
        try:
            from sentence_transformers import SentenceTransformer
            
            model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
            
            # Build description
            description = self._build_role_description(metadata)
            
            embedding = model.encode(description)
            return embedding.tolist()
            
        except ImportError:
            logger.warning("sentence-transformers not available, using rule-based vectors")
            return self._rule_based_role_vector(metadata)
    
    async def _generate_topology_vector(self, metadata: Dict) -> List[float]:
        """Generate topology-related vector"""
        try:
            from sentence_transformers import SentenceTransformer
            
            model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
            
            description = self._build_topology_description(metadata)
            
            embedding = model.encode(description)
            return embedding.tolist()
            
        except ImportError:
            return self._rule_based_topology_vector(metadata)
    
    async def _generate_security_vector(self, metadata: Dict) -> List[float]:
        """Generate security posture vector"""
        try:
            from sentence_transformers import SentenceTransformer
            
            model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
            
            description = self._build_security_description(metadata)
            
            embedding = model.encode(description)
            return embedding.tolist()
            
        except ImportError:
            return self._rule_based_security_vector(metadata)
    
    def _build_role_description(self, metadata: Dict) -> str:
        """Build text description for role classification"""
        parts = []
        
        if 'hostname' in metadata:
            parts.append(f"Device hostname: {metadata['hostname']}")
        
        if 'vendor' in metadata:
            parts.append(f"Vendor: {metadata['vendor']}")
        
        if 'device_type' in metadata:
            parts.append(f"Type: {metadata['device_type']}")
        
        # Count interfaces
        interfaces = metadata.get('interfaces', [])
        if interfaces:
            parts.append(f"Has {len(interfaces)} interfaces")
        
        # Check routing capability
        if 'routing' in metadata:
            parts.append("Supports routing protocols")
        
        # Check if it's a firewall
        vendor = metadata.get('vendor', '').lower()
        if 'firewall' in metadata.get('device_type', '').lower() or 'palo' in vendor or 'fortinet' in vendor:
            parts.append("Security appliance")
        
        return ". ".join(parts)
    
    def _build_topology_description(self, metadata: Dict) -> str:
        """Build text description for topology"""
        parts = []
        
        interfaces = metadata.get('interfaces', [])
        vlans = metadata.get('vlans', [])
        
        if interfaces:
            # Count by type
            layer3 = sum(1 for i in interfaces if i.get('ip_address'))
            layer2 = len(interfaces) - layer3
            parts.append(f"{layer3} L3 interfaces, {layer2} L2 interfaces")
        
        if vlans:
            parts.append(f"Member of {len(vlans)} VLANs")
        
        return ". ".join(parts) if parts else "Standard network device"
    
    def _build_security_description(self, metadata: Dict) -> str:
        """Build text description for security"""
        parts = []
        
        # Check for ACLs
        if metadata.get('acls'):
            parts.append(f"Has {len(metadata.get('acls', []))} ACLs")
        
        # Check for NAT
        if metadata.get('nat'):
            parts.append("Uses NAT")
        
        # Check for zones
        if metadata.get('zones'):
            parts.append(f"Has {len(metadata.get('zones', []))} security zones")
        
        return ". ".join(parts) if parts else "Standard security configuration"
    
    # Fallback rule-based vectors (768 dims filled with heuristics)
    def _rule_based_role_vector(self, metadata: Dict) -> List[float]:
        """Generate rule-based role vector"""
        import hashlib
        
        vector = [0.0] * 384  # MiniLM is 384 dims
        
        # Hash hostname to seed
        seed = int(hashlib.md5(metadata.get('hostname', '').encode()).hexdigest()[:8], 16)
        
        # Use seed to generate deterministic random-looking vector
        for i in range(min(len(vector), 384)):
            vector[i] = ((seed * (i + 1)) % 1000) / 1000.0
        
        return vector
    
    def _rule_based_topology_vector(self, metadata: Dict) -> List[float]:
        return [0.0] * 384
    
    def _rule_based_security_vector(self, metadata: Dict) -> List[float]:
        return [0.0] * 384
