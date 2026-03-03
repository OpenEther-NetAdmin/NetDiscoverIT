import pytest
from agent.sanitizer.token_mapper import TokenMapper, TokenType


def test_token_mapper_returns_correct_token():
    mapper = TokenMapper()
    assert mapper.get_token(TokenType.IPV4) == "<ip_address>"
    assert mapper.get_token(TokenType.IPV6) == "<ipv6_address>"
    assert mapper.get_token(TokenType.HOSTNAME) == "<hostname>"
    assert mapper.get_token(TokenType.PASSWORD) == "<password>"


def test_token_mapper_returns_default_for_unknown():
    mapper = TokenMapper()
    assert mapper.get_token("unknown_type") == "<unknown_type>"


def test_token_mapper_custom_tokens():
    custom_tokens = {"ipv4": "[IP]"}
    mapper = TokenMapper(custom_tokens=custom_tokens)
    assert mapper.get_token(TokenType.IPV4) == "[IP]"


def test_token_mapper_string_enum_values():
    """Test that string token types matching enum values work correctly"""
    mapper = TokenMapper()
    assert mapper.get_token("ipv4") == "<ip_address>"
    assert mapper.get_token("ipv6") == "<ipv6_address>"
    assert mapper.get_token("hostname") == "<hostname>"
    assert mapper.get_token("password") == "<password>"


def test_token_mapper_custom_tokens_enum_keys():
    """Test that custom tokens work with TokenType enum keys (not just strings)"""
    custom_tokens = {TokenType.IPV4: "[IP]", TokenType.HOSTNAME: "[HOST]"}
    mapper = TokenMapper(custom_tokens=custom_tokens)
    assert mapper.get_token(TokenType.IPV4) == "[IP]"
    assert mapper.get_token("ipv4") == "[IP]"
    assert mapper.get_token(TokenType.HOSTNAME) == "[HOST]"
    assert mapper.get_token("hostname") == "[HOST]"
