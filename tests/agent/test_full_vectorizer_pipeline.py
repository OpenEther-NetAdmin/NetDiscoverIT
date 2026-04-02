import pytest
from agent.vectorizer import DeviceVectorizer

class TestFullVectorizerPipeline:
    @pytest.fixture
    def vectorizer(self):
        config = {}
        return DeviceVectorizer(config)
    
    @pytest.fixture
    def sample_metadata(self):
        """Sample metadata as would come from normalizer + sanitizer.

        Note: IP addresses shown are illustrative. In production, these would be
        tokenized by the sanitizer before reaching the vectorizer (e.g., <ip_address>).
        """
        return {
            "hostname": "core-router-01",
            "vendor": "Cisco",
            "device_type": "router",
            "interfaces": [
                {"name": "Gi0/0", "ip_address": "10.0.0.1"},
                {"name": "Gi0/1", "ip_address": "10.0.1.1"},
                {"name": "Gi0/2"},  # L2 interface
            ],
            "vlans": [10, 20, 30],
            "routing": {"bgp": True, "ospf": False},
            "acls": ["ACL-001", "ACL-002"],
            "nat": True,
            "normalized_config": {
                "interfaces": [
                    {"name": "Gi0/0", "ip": "10.0.0.1", "mask": "255.255.255.0"},
                    {"name": "Gi0/1", "ip": "10.0.1.1", "mask": "255.255.255.0"}
                ],
                "bgp": {"asn": 65001, "neighbor_count": 1}
            }
        }
    
    def test_all_vectors_generated(self, vectorizer, sample_metadata):
        vectors = vectorizer.generate_vectors(sample_metadata)
        
        assert 'device_role' in vectors
        assert 'topology' in vectors
        assert 'security' in vectors
        assert 'config' in vectors
        
        for vec_name, vec in vectors.items():
            assert len(vec) == 768, f"{vec_name} should be 768 dims"
    
    def test_deterministic_output(self, vectorizer, sample_metadata):
        """Same input should produce same output"""
        vectors1 = vectorizer.generate_vectors(sample_metadata)
        vectors2 = vectorizer.generate_vectors(sample_metadata)
        
        for vec_name in vectors1:
            assert vectors1[vec_name] == vectors2[vec_name], f"{vec_name} should be deterministic"