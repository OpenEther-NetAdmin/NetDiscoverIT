import pytest
from datetime import datetime
from app.api.schemas import DeviceMetadata
from pydantic import ValidationError


class TestDeviceMetadata:
    """Tests for DeviceMetadata JSONB field validation"""

    def test_valid_metadata_passes_validation(self):
        """Valid metadata with non-privacy fields should pass validation"""
        metadata = {
            "interfaces": [{"name": "eth0", "ip": "192.168.1.1"}],
            "vlans": [{"id": 10, "name": "VLAN10"}],
            "routing_table": [{"dest": "0.0.0.0", "gateway": "192.168.1.1"}],
            "running_services": ["sshd", "nginx"],
            "installed_packages": [{"name": "openssh", "version": "8.0"}],
            "discovery_method": "snmp",
            "discovery_timestamp": "2024-01-15T10:00:00Z",
            "normalized_by": "agent-001",
        }
        result = DeviceMetadata(**metadata)
        assert result.discovery_method == "snmp"
        assert len(result.interfaces) == 1

    def test_default_values_work(self):
        """Empty metadata should use default values"""
        metadata = DeviceMetadata()
        assert metadata.interfaces == []
        assert metadata.vlans == []
        assert metadata.routing_table == []
        assert metadata.running_services == []
        assert metadata.installed_packages == []
        assert metadata.discovery_method is None
        assert metadata.discovery_timestamp is None
        assert metadata.normalized_by is None
        assert metadata.extra == {}


class TestDeviceMetadataPrivacyFields:
    """Tests verifying privacy-sensitive fields are NOT in DeviceMetadata"""

    def test_acl_entries_not_allowed(self):
        """acl_entries must not be accepted - privacy architecture prohibits ACL data in cloud"""
        metadata = {"acl_entries": [{"rule": "permit ip any any"}]}
        with pytest.raises(ValidationError) as exc_info:
            DeviceMetadata(**metadata)
        assert "acl_entries" in str(exc_info.value)

    def test_firewall_rules_not_allowed(self):
        """firewall_rules must not be accepted - privacy architecture prohibits firewall data in cloud"""
        metadata = {"firewall_rules": [{"action": "allow", "port": 443}]}
        with pytest.raises(ValidationError) as exc_info:
            DeviceMetadata(**metadata)
        assert "firewall_rules" in str(exc_info.value)

    def test_users_not_allowed(self):
        """users must not be accepted - privacy architecture prohibits user data in cloud"""
        metadata = {"users": [{"username": "admin", "uid": 1000}]}
        with pytest.raises(ValidationError) as exc_info:
            DeviceMetadata(**metadata)
        assert "users" in str(exc_info.value)

    def test_acl_firewall_users_combined_not_allowed(self):
        """Combined privacy fields must all be rejected"""
        metadata = {
            "interfaces": [{"name": "eth0"}],
            "acl_entries": [{"rule": "permit ip any any"}],
            "firewall_rules": [{"action": "allow"}],
            "users": [{"username": "admin"}],
        }
        with pytest.raises(ValidationError) as exc_info:
            DeviceMetadata(**metadata)
        error_str = str(exc_info.value)
        assert "acl_entries" in error_str or "firewall_rules" in error_str or "users" in error_str

    def test_extra_fields_are_allowed(self):
        """Extra fields should be allowed without raising validation errors"""
        metadata = {
            "custom_field": "custom_value",
            "another_field": {"nested": "value"},
        }
        result = DeviceMetadata(**metadata)
        assert result.custom_field == "custom_value"
        assert result.another_field == {"nested": "value"}

    def test_partial_metadata_with_defaults(self):
        """Partial metadata should fill in defaults"""
        metadata = {
            "interfaces": [{"name": "lo"}],
            "discovery_method": "ping",
        }
        result = DeviceMetadata(**metadata)
        assert result.interfaces == [{"name": "lo"}]
        assert result.vlans == []
        assert result.discovery_method == "ping"

    def test_discovery_timestamp_as_datetime(self):
        """discovery_timestamp should accept datetime objects"""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        metadata = {"discovery_timestamp": dt}
        result = DeviceMetadata(**metadata)
        assert result.discovery_timestamp == dt
