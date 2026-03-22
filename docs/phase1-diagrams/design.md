%%{ init: { "theme": "base", "themeVariables": { "primaryColor": "#4f46e5", "lineColor": "#6b7280", "secondaryColor": "#10b981", "tertiaryColor": "#f59e0b" } } }%%

```mermaid
classDiagram
    %% Sanitizer Module
    class ConfigSanitizer {
        +org_id: str
        +enable_tier1: bool
        +enable_tier2: bool
        +enable_tier3: bool
        +token_mapper: TokenMapper
        +redaction_logger: RedactionLogger
        +tier_resolver: TierResolver
        +tier2_sanitizer: SectionRegexSanitizer
        +tier3_sanitizer: AggressiveRegexSanitizer
        +sanitize(config, device_type)
        +register_template(device_type)
    }
    
    class TierResolver {
        +_available_templates: Set[str]
        +register_template(device_type)
        +has_template(device_type)
        +resolve(config_text, device_type)
    }
    
    class Tier2Result {
        +sanitized_text: str
        +redactions: List[dict]
    }
    
    class Tier3Result {
        +sanitized_text: str
        +redactions: List[dict]
    }
    
    ConfigSanitizer --> TierResolver
    ConfigSanitizer --> SectionRegexSanitizer
    ConfigSanitizer --> AggressiveRegexSanitizer
    ConfigSanitizer --> TokenMapper
    ConfigSanitizer --> RedactionLogger
    
    SectionRegexSanitizer --> Tier2Result
    AggressiveRegexSanitizer --> Tier3Result
    
    %% Token System
    class TokenMapper {
        +tokens: Dict[TokenType, str]
        +get_token(data_type)
    }
    
    class TokenType {
        <<enumeration>>
        IPV4
        IPV6
        PASSWORD
        SECRET
        COMMUNITY
        BGP_AS
        VLAN_ID
        MAC_ADDRESS
    }
    
    TokenMapper --> TokenType
    
    %% Logging
    class RedactionLogger {
        +org_id: str
        +entries: List[RedactionEntry]
        +_tier_used: Optional[int]
        +log(original, replacement, line, data_type, tier)
        +get_redaction_map()
        +set_tiers_used(tiers)
    }
    
    class RedactionEntry {
        +data_type: str
        +line: int
        +token: str
        +original_hash: str
        +tier: int
    }
    
    RedactionLogger --> RedactionEntry
    
    %% Tier Classes
    class SectionRegexSanitizer {
        +SECTION_PATTERNS: Dict
        +SECTION_RULES: Dict
        +GLOBAL_PATTERNS: List
        +token_mapper: TokenMapper
        +_detect_sections(config_text)
        +sanitize(config_text)
    }
    
    class AggressiveRegexSanitizer {
        +PATTERNS: List[Tuple]
        +token_mapper: TokenMapper
        +sanitize(config_text)
    }
    
    class TextFSMSanitizer {
        +_templates: Dict
        +has_template(device_type)
        +sanitize(config_text, device_type)
    }
    
    class TemplateNotFoundError {
        <<exception>>
    }
    
    TextFSMSanitizer --> TemplateNotFoundError
    
    %% Relationships Legend
    note for ConfigSanitizer "Orchestrates tiered<br/>sanitization pipeline"
    note for TierResolver "Determines which tier<br/>to use based on<br/>device type & config"
    note for TokenMapper "Maps data types to<br/>placeholder tokens"
    note for RedactionLogger "Audit trail - tracks<br/>redactions without<br/>storing secrets"
```

### Module Design Notes

**ConfigSanitizer (Orchestrator)**
- Coordinates the 3-tier sanitization pipeline
- Uses TierResolver to determine which tiers to apply
- Accepts custom tokens for enterprise deployments

**TierResolver**
- Priority: Tier 1 (if template exists) → Tier 2 (if structure detected) → Tier 3 (fallback)
- Allows registration of TextFSM templates per device type

**TokenMapper**
- Provides consistent placeholder tokens
- Default tokens: `<ip_address>`, `<password>`, `<secret>`, etc.
- Supports custom token overrides

**RedactionLogger**
- Creates audit trail for compliance
- Stores hashes (not actual values) for verification
- Tracks which tier was used for each redaction

**Sanitizer Tiers**
- **SectionRegexSanitizer (Tier 2):** Detects config sections (interface, router bgp) and applies targeted rules
- **AggressiveRegexSanitizer (Tier 3):** Catch-all patterns for common sensitive data
- **TextFSMSanitizer (Tier 1):** Stub for future template-based precision