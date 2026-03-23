"""
Device Vectorizer
Generates embeddings for ML analysis
"""

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

MODEL_NAME = 'sentence-transformers/all-mpnet-base-v2'
VECTOR_DIM = 768


class DeviceVectorizer:
    """Generates vector embeddings for devices"""

    def __init__(self, config):
        self.config = config
        self._model = None

    @property
    def model(self):
        """Lazy-loading model property"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(MODEL_NAME)
            except ImportError:
                logger.warning("sentence-transformers not available")
                self._model = None
        return self._model

    async def generate_vectors(self, device_metadata: Dict) -> Dict:
        """Generate vector embeddings for a device"""
        vectors = {}

        vectors['device_role'] = await self._generate_role_vector(device_metadata)
        vectors['topology'] = await self._generate_topology_vector(device_metadata)
        vectors['security'] = await self._generate_security_vector(device_metadata)
        vectors['config'] = await self._generate_config_vector(device_metadata)

        return vectors

    async def _generate_role_vector(self, metadata: Dict) -> List[float]:
        """Generate device role vector"""
        if self.model:
            description = self._build_role_description(metadata)
            embedding = self.model.encode(description)
            return embedding.tolist()
        return self._rule_based_role_vector(metadata)

    async def _generate_topology_vector(self, metadata: Dict) -> List[float]:
        """Generate topology-related vector"""
        if self.model:
            description = self._build_topology_description(metadata)
            embedding = self.model.encode(description)
            return embedding.tolist()
        return self._rule_based_topology_vector(metadata)

    async def _generate_security_vector(self, metadata: Dict) -> List[float]:
        """Generate security posture vector"""
        if self.model:
            description = self._build_security_description(metadata)
            embedding = self.model.encode(description)
            return embedding.tolist()
        return self._rule_based_security_vector(metadata)

    async def _generate_config_vector(self, metadata: Dict) -> List[float]:
        """Generate config vector from normalized config"""
        if self.model:
            normalized_config = metadata.get('normalized_config')
            if normalized_config:
                description = self._build_config_description(normalized_config)
                embedding = self.model.encode(description)
                return embedding.tolist()
        return self._rule_based_config_vector(metadata)

    def _build_role_description(self, metadata: Dict) -> str:
        """Build text description for role classification"""
        parts = []

        if 'hostname' in metadata:
            parts.append(f"Device hostname: {metadata['hostname']}")

        if 'vendor' in metadata:
            parts.append(f"Vendor: {metadata['vendor']}")

        if 'device_type' in metadata:
            parts.append(f"Type: {metadata['device_type']}")

        interfaces = metadata.get('interfaces', [])
        if interfaces:
            parts.append(f"Has {len(interfaces)} interfaces")

        if 'routing' in metadata:
            parts.append("Supports routing protocols")

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
            layer3 = sum(1 for i in interfaces if i.get('ip_address'))
            layer2 = len(interfaces) - layer3
            parts.append(f"{layer3} L3 interfaces, {layer2} L2 interfaces")

        if vlans:
            parts.append(f"Member of {len(vlans)} VLANs")

        return ". ".join(parts) if parts else "Standard network device"

    def _build_security_description(self, metadata: Dict) -> str:
        """Build text description for security"""
        parts = []

        if metadata.get('acls'):
            parts.append(f"Has {len(metadata.get('acls', []))} ACLs")

        if metadata.get('nat'):
            parts.append("Uses NAT")

        if metadata.get('zones'):
            parts.append(f"Has {len(metadata.get('zones', []))} security zones")

        return ". ".join(parts) if parts else "Standard security configuration"

    def _build_config_description(self, normalized_config: Dict) -> str:
        """Build text description from normalized config"""
        parts = []

        interfaces = normalized_config.get('interfaces', [])
        if interfaces:
            for iface in interfaces:
                name = iface.get('name', '')
                if name:
                    parts.append(f"Interface {name}")
                if iface.get('ip_address'):
                    parts.append(f"has IP {iface.get('ip_address')}")

        if normalized_config.get('hostname'):
            parts.append(f"Hostname: {normalized_config.get('hostname')}")

        if normalized_config.get('vendor'):
            parts.append(f"Vendor: {normalized_config.get('vendor')}")

        if normalized_config.get('routing_protocols'):
            parts.append(f"Routing: {normalized_config.get('routing_protocols')}")

        return ". ".join(parts) if parts else "Device configuration"

    def _serialize_config_dict(self, normalized_config: Dict) -> str:
        """Serialize config dict to string for embedding"""
        import json

        def flatten(d, parent_key=''):
            items = []
            for k, v in d.items():
                new_key = f"{parent_key}_{k}" if parent_key else k
                if isinstance(v, dict):
                    items.extend(flatten(v, new_key).items())
                elif isinstance(v, list):
                    for i, item in enumerate(v):
                        if isinstance(item, dict):
                            items.extend(flatten(item, f"{new_key}_{i}").items())
                        else:
                            items.append((f"{new_key}_{i}", item))
                else:
                    items.append((new_key, str(v)))
            return dict(items)

        flattened = flatten(normalized_config)
        return json.dumps(flattened, sort_keys=True)

    def _rule_based_role_vector(self, metadata: Dict) -> List[float]:
        """Generate rule-based role vector"""
        import hashlib

        vector = [0.0] * VECTOR_DIM

        seed = int(hashlib.md5(metadata.get('hostname', '').encode()).hexdigest()[:8], 16)

        for i in range(VECTOR_DIM):
            vector[i] = ((seed * (i + 1)) % 1000) / 1000.0

        return vector

    def _rule_based_topology_vector(self, metadata: Dict) -> List[float]:
        return [0.0] * VECTOR_DIM

    def _rule_based_security_vector(self, metadata: Dict) -> List[float]:
        return [0.0] * VECTOR_DIM

    def _rule_based_config_vector(self, metadata: Dict) -> List[float]:
        normalized_config = metadata.get('normalized_config', {})
        import hashlib

        config_str = self._serialize_config_dict(normalized_config)
        seed = int(hashlib.md5(config_str.encode()).hexdigest()[:8], 16)

        vector = [0.0] * VECTOR_DIM
        for i in range(VECTOR_DIM):
            vector[i] = ((seed * (i + 1)) % 1000) / 1000.0

        return vector