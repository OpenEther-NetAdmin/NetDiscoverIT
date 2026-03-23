import pytest
from agent.vectorizer import DeviceVectorizer

class TestVectorizerDimensions:
    @pytest.fixture
    def vectorizer(self):
        config = {}
        return DeviceVectorizer(config)

    @pytest.mark.asyncio
    async def test_role_vector_is_768_dims(self, vectorizer):
        metadata = {"hostname": "test-switch", "vendor": "Cisco", "device_type": "switch"}
        vectors = await vectorizer.generate_vectors(metadata)
        assert len(vectors['device_role']) == 768

    @pytest.mark.asyncio
    async def test_topology_vector_is_768_dims(self, vectorizer):
        metadata = {"interfaces": [{"name": "Gi0/1"}]}
        vectors = await vectorizer.generate_vectors(metadata)
        assert len(vectors['topology']) == 768

    @pytest.mark.asyncio
    async def test_security_vector_is_768_dims(self, vectorizer):
        metadata = {"acls": ["acl1"]}
        vectors = await vectorizer.generate_vectors(metadata)
        assert len(vectors['security']) == 768

    @pytest.mark.asyncio
    async def test_config_vector_is_768_dims(self, vectorizer):
        metadata = {"normalized_config": {"interfaces": [{"name": "Gi0/1"}]}}
        vectors = await vectorizer.generate_vectors(metadata)
        assert len(vectors['config']) == 768