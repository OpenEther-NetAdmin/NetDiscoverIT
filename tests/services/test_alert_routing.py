import pytest


def test_alert_routing_uses_safe_deserialization():
    """eval() on decrypted credentials allows RCE - must use json.loads."""
    from app.services.alert_routing import _deserialize_alert_config

    mock_decrypted = '{"key": "value"}'
    result = _deserialize_alert_config(mock_decrypted)
    assert isinstance(result, dict)
    assert result == {"key": "value"}


def test_deserialize_alert_config_invalid_json():
    """Invalid JSON should raise ValueError."""
    from app.services.alert_routing import _deserialize_alert_config

    with pytest.raises(ValueError, match="Invalid JSON"):
        _deserialize_alert_config("{key: value}")


def test_deserialize_alert_config_non_dict_json():
    """Non-dict JSON should raise TypeError."""
    from app.services.alert_routing import _deserialize_alert_config

    with pytest.raises(TypeError, match="must be a JSON object"):
        _deserialize_alert_config('"string_value"')

    with pytest.raises(TypeError, match="must be a JSON object"):
        _deserialize_alert_config('["list", "items"]')


def test_deserialize_alert_config_empty_string():
    """Empty string should raise ValueError."""
    from app.services.alert_routing import _deserialize_alert_config

    with pytest.raises(ValueError, match="Invalid JSON"):
        _deserialize_alert_config("")
