"""
Tests for VectorUploader - ensuring no raw config text is uploaded
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from agent.uploader import VectorUploader


class TestUploadPayloadPrivacy:
    """Test that upload payloads don't contain raw config text"""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.API_ENDPOINT = "https://api.example.com"
        config.API_KEY = "test-api-key"
        return config

    @pytest.fixture
    def uploader(self, mock_config):
        return VectorUploader(mock_config)

    @pytest.fixture
    def sample_devices_with_full_sanitized_output(self):
        return [
            {
                "device_id": "router-01",
                "metadata": {
                    "sanitized": "interface GigabitEthernet0/1\n description ***PRIVATE***\n ip address 192.168.1.1 255.255.255.0",
                    "redaction_log": {
                        "org_id": "test-org",
                        "tier_used": 2,
                        "sanitized_at": "2026-03-28T10:00:00Z",
                        "replacements": [
                            {
                                "type": "description",
                                "line": 2,
                                "original_hash": "abc123def456",
                                "token": "***PRIVATE***",
                                "tier": 2
                            }
                        ]
                    }
                },
                "vectors": [0.1, 0.2, 0.3]
            }
        ]

    @pytest.mark.asyncio
    async def test_metadata_does_not_contain_raw_config_text(
        self, uploader, sample_devices_with_full_sanitized_output
    ):
        """Verify that device metadata doesn't contain raw config text after upload processing"""
        devices = sample_devices_with_full_sanitized_output

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            await uploader.upload_vectors(devices)

            uploaded_payload = mock_instance.post.call_args.kwargs["json"]

            for device in uploaded_payload["devices"]:
                metadata = device.get("metadata", {})
                assert "sanitized" not in metadata, \
                    "metadata contains 'sanitized' config text - privacy leak!"
                assert "sanitized_text" not in metadata, \
                    "metadata contains 'sanitized_text' - privacy leak!"

    @pytest.mark.asyncio
    async def test_metadata_only_contains_redaction_log(
        self, uploader, sample_devices_with_full_sanitized_output
    ):
        """Verify metadata only contains redaction_log for structured data"""
        devices = sample_devices_with_full_sanitized_output

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            await uploader.upload_vectors(devices)

            uploaded_payload = mock_instance.post.call_args.kwargs["json"]

            for device in uploaded_payload["devices"]:
                metadata = device.get("metadata", {})
                if isinstance(metadata, dict):
                    assert "redaction_log" in metadata, \
                        "metadata should contain 'redaction_log'"

    @pytest.mark.asyncio
    async def test_redaction_log_has_proper_structure(
        self, uploader, sample_devices_with_full_sanitized_output
    ):
        """Verify redaction_log contains hashes and counts, not original config text"""
        devices = sample_devices_with_full_sanitized_output

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            await uploader.upload_vectors(devices)

            uploaded_payload = mock_instance.post.call_args.kwargs["json"]

            for device in uploaded_payload["devices"]:
                metadata = device.get("metadata", {})
                redaction_log = metadata.get("redaction_log", {})

                assert "replacements" in redaction_log
                for replacement in redaction_log["replacements"]:
                    assert "original_hash" in replacement
                    assert len(replacement["original_hash"]) <= 16
                    assert "token" in replacement

    @pytest.mark.asyncio
    async def test_no_interface_config_in_uploaded_payload(
        self, uploader, sample_devices_with_full_sanitized_output
    ):
        """Verify 'interface' config lines don't appear in uploaded payload"""
        devices = sample_devices_with_full_sanitized_output

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            await uploader.upload_vectors(devices)

            uploaded_payload = mock_instance.post.call_args.kwargs["json"]
            payload_str = str(uploaded_payload)

            assert "GigabitEthernet" not in payload_str, \
                "Config interface details found in upload - privacy leak!"
            assert "ip address 192.168" not in payload_str, \
                "IP addresses found in upload - privacy leak!"


class TestAsyncContext:
    """Test that upload_vectors works correctly in async context"""

    @pytest.fixture
    def mock_config(self):
        config = MagicMock()
        config.API_ENDPOINT = "https://api.example.com"
        config.API_KEY = "test-api-key"
        return config

    @pytest.fixture
    def uploader(self, mock_config):
        return VectorUploader(mock_config)

    @pytest.mark.asyncio
    async def test_upload_vectors_works_in_async_context(self, uploader):
        """Verify upload_vectors does not raise RuntimeError when called from async context"""
        devices = [
            {
                "device_id": "router-01",
                "metadata": {"redaction_log": {}},
                "vectors": [0.1, 0.2, 0.3]
            }
        ]

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"status": "ok"}
            mock_instance = AsyncMock()
            mock_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await uploader.upload_vectors(devices)
            assert result == {"status": "ok"}
