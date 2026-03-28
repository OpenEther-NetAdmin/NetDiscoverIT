import pytest


def test_alert_routing_uses_safe_deserialization():
    """pickle.loads on decrypted credentials allows RCE - must use json.loads."""
    from app.services.alert_routing import _deserialize_alert_config

    mock_decrypted = '{"key": "value"}'
    result = _deserialize_alert_config(mock_decrypted)
    assert isinstance(result, dict)
    assert result == {"key": "value"}
