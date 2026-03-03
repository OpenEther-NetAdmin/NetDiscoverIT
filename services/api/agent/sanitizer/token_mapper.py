from enum import Enum
from typing import Optional


class TokenType(str, Enum):
    IPV4 = "ipv4"
    IPV6 = "ipv6"
    HOSTNAME = "hostname"
    FQDN = "fqdn"
    PASSWORD = "password"
    SECRET = "secret"
    COMMUNITY = "community"
    BGP_AS = "bgp_as"
    VLAN_ID = "vlan_id"
    MAC_ADDRESS = "mac"


DEFAULT_TOKENS = {
    TokenType.IPV4: "<ip_address>",
    TokenType.IPV6: "<ipv6_address>",
    TokenType.HOSTNAME: "<hostname>",
    TokenType.FQDN: "<fqdn>",
    TokenType.PASSWORD: "<password>",
    TokenType.SECRET: "<secret>",
    TokenType.COMMUNITY: "<community_string>",
    TokenType.BGP_AS: "<as_number>",
    TokenType.VLAN_ID: "<vlan_id>",
    TokenType.MAC_ADDRESS: "<mac_address>",
}


class TokenMapper:
    """Maps data types to placeholder tokens for sanitization"""

    def __init__(self, custom_tokens: Optional[dict] = None):
        self.tokens = {**DEFAULT_TOKENS}
        if custom_tokens:
            for key, value in custom_tokens.items():
                token_type = key if isinstance(key, TokenType) else TokenType(key)
                self.tokens[token_type] = value

    def get_token(self, data_type: str | TokenType) -> str:
        """Get placeholder token for a data type"""
        if isinstance(data_type, str):
            try:
                data_type = TokenType(data_type)
            except ValueError:
                return f"<{data_type}>"
        return self.tokens.get(data_type, f"<{data_type}>")
