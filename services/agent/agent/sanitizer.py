"""
Config Sanitizer
Removes PII before transmission to cloud
"""

import re
import logging

logger = logging.getLogger(__name__)


class ConfigSanitizer:
    """Sanitizes configuration to remove sensitive information"""
    
    # Patterns to scrub
    SCRUB_PATTERNS = [
        # Passwords
        (r'password\s+(\S+)', 'password ***'),
        (r'username\s+\S+\s+password\s+\S+', 'username *** password ***'),
        (r'secret\s+\d+\s+\S+', 'secret ***'),
        
        # SNMP
        (r'snmp-server community (\S+)', 'snmp-server community ***'),
        (r'community (\S+)', 'community ***'),
        
        # Keys
        (r'(rsa|dsa|ecdsa) (\d+) (\S+)', r'\1 \2 ***'),
        (r'ip ssh (\S+) (\S+)', 'ip ssh *** ***'),
        
        # API keys
        (r'api-key\s+(\S+)', 'api-key ***'),
        (r'api_key\s+(\S+)', 'api_key ***'),
        
        # Basic auth
        (r'username (\S+)', 'username ***'),
        (r'auth (\S+) (\S+)', 'auth *** ***'),
        
        # Tunnel keys
        (r'tunnel key (\S+)', 'tunnel key ***'),
    ]
    
    # Fields to remove entirely
    REMOVE_FIELDS = [
        'password',
        'secret',
        'community',
        'api_key',
        'private_key',
        'passphrase',
    ]
    
    def sanitize(self, config_data: dict) -> dict:
        """Sanitize a config dictionary"""
        if isinstance(config_data, str):
            # It's raw config text
            return self._sanitize_text(config_data)
        elif isinstance(config_data, dict):
            # It's already parsed JSON
            return self._sanitize_dict(config_data)
        else:
            return config_data
    
    def _sanitize_text(self, text: str) -> dict:
        """Sanitize raw config text"""
        sanitized = text
        
        for pattern, replacement in self.SCRUB_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        
        return {"sanitized_config": sanitized, "was_sanitized": True}
    
    def _sanitize_dict(self, data: dict, depth: int = 0) -> dict:
        """Sanitize a dictionary"""
        if depth > 10:  # Prevent infinite recursion
            return data
        
        sanitized = {}
        
        for key, value in data.items():
            key_lower = key.lower()
            
            # Skip sensitive fields
            if key_lower in self.REMOVE_FIELDS:
                sanitized[key] = "***"
                continue
            
            # Recurse into nested dicts
            if isinstance(value, dict):
                sanitized[key] = self._sanitize_dict(value, depth + 1)
            
            # Recurse into lists
            elif isinstance(value, list):
                sanitized[key] = [
                    self._sanitize_dict(item, depth + 1) if isinstance(item, dict) else item
                    for item in value
                ]
            
            # Sanitize string values
            elif isinstance(value, str):
                sanitized[key] = self._sanitize_string(value)
            
            else:
                sanitized[key] = value
        
        return sanitized
    
    def _sanitize_string(self, text: str) -> str:
        """Sanitize a string value"""
        sanitized = text
        
        for pattern, replacement in self.SCRUB_PATTERNS:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)
        
        return sanitized
    
    def get_scrub_report(self, original: str, sanitized: dict) -> dict:
        """Generate a report of what was scrubbed"""
        original_len = len(original)
        
        # Rough estimate of what was removed
        if isinstance(sanitized, dict):
            sanitized_text = str(sanitized)
        else:
            sanitized_text = str(sanitized)
        
        return {
            "original_length": original_len,
            "sanitized_length": len(sanitized_text),
            "fields_scrubbed": len(self.REMOVE_FIELDS),
            "patterns_matched": len(self.SCRUB_PATTERNS)
        }
