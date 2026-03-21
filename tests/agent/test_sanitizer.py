import pytest
from agent.sanitizer.config_sanitizer import ConfigSanitizer


class TestConfigSanitizerBasic:
    def test_sanitize_removes_password_from_text(self):
        sanitizer = ConfigSanitizer(org_id="test-org")
        config = "username admin password Secret123"
        result = sanitizer.sanitize(config)
        assert "<password>" in result["sanitized"]
        assert "Secret123" not in result["sanitized"]

    def test_sanitize_returns_redaction_log(self):
        sanitizer = ConfigSanitizer(org_id="test-org")
        config = "password admin"
        result = sanitizer.sanitize(config)
        assert "redaction_log" in result
        assert len(result["redaction_log"]["replacements"]) > 0


class TestConfigSanitizerDict:
    def test_sanitize_dict_basic(self):
        sanitizer = ConfigSanitizer(org_id="test-org")
        config = {"username": "admin", "password": "secret123"}
        result = sanitizer.sanitize(config)
        assert result["sanitized"]["password"] == "<password>"

    def test_sanitize_dict_nested(self):
        sanitizer = ConfigSanitizer(org_id="test-org")
        config = {
            "device": {
                "credentials": {
                    "username": "admin",
                    "password": "secret123"
                }
            }
        }
        result = sanitizer.sanitize(config)
        assert result["sanitized"]["device"]["credentials"]["password"] == "<password>"

    def test_sanitize_dict_list(self):
        sanitizer = ConfigSanitizer(org_id="test-org")
        config = {
            "users": [
                {"name": "admin", "password": "pass1"},
                {"name": "user", "password": "pass2"}
            ]
        }
        result = sanitizer.sanitize(config)
        assert result["sanitized"]["users"][0]["password"] == "<password>"
        assert result["sanitized"]["users"][1]["password"] == "<password>"


class TestConfigSanitizerTier2:
    def test_aws_access_key_detection(self):
        sanitizer = ConfigSanitizer(org_id="test-org", enable_tier2=True)
        config = "AKIAIOSFODNN7EXAMPLE key123"
        result = sanitizer.sanitize(config)
        assert "<secret>" in result["sanitized"]
        assert "AKIAIOSFODNN7EXAMPLE" not in result["sanitized"]

    def test_aws_access_key_redaction_log(self):
        sanitizer = ConfigSanitizer(org_id="test-org", enable_tier2=True)
        config = "AKIAIOSFODNN7EXAMPLE"
        result = sanitizer.sanitize(config)
        redactions = result["redaction_log"]["replacements"]
        aws_redactions = [r for r in redactions if r.get("type") == "secret" and r.get("tier") == 2]
        assert len(aws_redactions) > 0

    def test_ssh_private_key_detection(self):
        sanitizer = ConfigSanitizer(org_id="test-org", enable_tier2=True)
        config = "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJBAKj34GkxvhDkrdecUm\n-----END RSA PRIVATE KEY-----"
        result = sanitizer.sanitize(config)
        assert "<secret>" in result["sanitized"]
        assert "BEGIN RSA PRIVATE KEY" not in result["sanitized"]

    def test_bearer_token_detection(self):
        sanitizer = ConfigSanitizer(org_id="test-org", enable_tier2=True)
        config = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = sanitizer.sanitize(config)
        assert "<secret>" in result["sanitized"]

    def test_basic_auth_detection(self):
        sanitizer = ConfigSanitizer(org_id="test-org", enable_tier2=True)
        config = "Authorization: Basic dXNlcm5hbWU6cGFzc3dvcmQ="
        result = sanitizer.sanitize(config)
        assert "<secret>" in result["sanitized"]

    def test_api_key_detection(self):
        sanitizer = ConfigSanitizer(org_id="test-org", enable_tier2=True)
        config = 'api_key = "sk_live_abcdefghijklmnopqrst"'
        result = sanitizer.sanitize(config)
        assert "<secret>" in result["sanitized"]

    def test_cisco_enable_password_detection(self):
        sanitizer = ConfigSanitizer(org_id="test-org", enable_tier2=True)
        config = "enable password SuperSecret123"
        result = sanitizer.sanitize(config)
        assert "<password>" in result["sanitized"]
        assert "SuperSecret123" not in result["sanitized"]


class TestConfigSanitizerTiers:
    def test_tier_disabled(self):
        sanitizer = ConfigSanitizer(org_id="test-org", enable_tier3=False)
        config = "password test123"
        result = sanitizer.sanitize(config)
        assert "test123" in result["sanitized"]

    def test_tier_all_enabled(self):
        sanitizer = ConfigSanitizer(
            org_id="test-org",
            enable_tier1=True,
            enable_tier2=True,
            enable_tier3=True
        )
        config = "password test123"
        result = sanitizer.sanitize(config)
        assert "test123" not in result["sanitized"]


class TestConfigSanitizerEdgeCases:
    def test_empty_string(self):
        sanitizer = ConfigSanitizer(org_id="test-org")
        result = sanitizer.sanitize("")
        assert result["sanitized"] == ""

    def test_empty_dict(self):
        sanitizer = ConfigSanitizer(org_id="test-org")
        result = sanitizer.sanitize({})
        assert result["sanitized"] == {}

    def test_none_value_in_dict(self):
        sanitizer = ConfigSanitizer(org_id="test-org")
        config = {"key": None, "password": "secret"}
        result = sanitizer.sanitize(config)
        assert result["sanitized"]["key"] is None
        assert result["sanitized"]["password"] == "<password>"

    def test_non_string_dict_values(self):
        sanitizer = ConfigSanitizer(org_id="test-org")
        config = {
            "enabled": True,
            "count": 42,
            "rate": 3.14,
            "password": "secret"
        }
        result = sanitizer.sanitize(config)
        assert result["sanitized"]["enabled"] is True
        assert result["sanitized"]["count"] == 42
        assert result["sanitized"]["rate"] == 3.14
        assert result["sanitized"]["password"] == "<password>"
