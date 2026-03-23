import pytest
from agent.agent.vectorizer import DeviceVectorizer

class TestVectorizerDimensions:
    @pytest.fixture
    def vectorizer(self):
        config = {}
        return DeviceVectorizer(config)

    def test_role_vector_is_768_dims(self, vectorizer):
        metadata = {"hostname": "test-switch", "vendor": "Cisco", "device_type": "switch"}
        vectors = vectorizer.generate_vectors(metadata)
        assert len(vectors['device_role']) == 768

    def test_topology_vector_is_768_dims(self, vectorizer):
        metadata = {"interfaces": [{"name": "Gi0/1"}]}
        vectors = vectorizer.generate_vectors(metadata)
        assert len(vectors['topology']) == 768

    def test_security_vector_is_768_dims(self, vectorizer):
        metadata = {"acls": ["acl1"]}
        vectors = vectorizer.generate_vectors(metadata)
        assert len(vectors['security']) == 768

    def test_config_vector_is_768_dims(self, vectorizer):
        metadata = {"normalized_config": {"interfaces": [{"name": "Gi0/1"}]}}
        vectors = vectorizer.generate_vectors(metadata)
        assert len(vectors['config']) == 768