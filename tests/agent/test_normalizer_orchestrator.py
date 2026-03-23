from services.agent.agent.normalizer import normalize_command_output


def test_normalize_command_output_returns_canonical_payload():
    result = normalize_command_output("cisco_ios", "show version", "raw output")
    assert result.parser_method in {"textfsm", "fallback"}
