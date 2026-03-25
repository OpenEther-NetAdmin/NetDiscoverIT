import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

HASH_TRUNCATION = 16


@dataclass
class RedactionEntry:
    """Single redaction record"""
    data_type: str
    line: int
    token: str
    original_hash: str
    tier: int


class RedactionLogger:
    """Logs redactions for audit trail"""
    
    def __init__(self, org_id: str):
        self.org_id = org_id
        self.entries: List[RedactionEntry] = []
        self._tier_used: Optional[int] = None
    
    def log(self, original: str, replacement: str, line: int,
            data_type: str, tier: int) -> RedactionEntry:
        """Log a single redaction"""
        original_hash = hashlib.sha256(original.encode()).hexdigest()[:HASH_TRUNCATION]
        
        entry = RedactionEntry(
            data_type=data_type,
            line=line,
            token=replacement,
            original_hash=original_hash,
            tier=tier
        )
        self.entries.append(entry)
        
        # Track highest tier used (lower number = more precise)
        if self._tier_used is None or tier < self._tier_used:
            self._tier_used = tier
        
        return entry
    
    def get_redaction_map(self) -> dict:
        """Get complete redaction map for audit"""
        return {
            "org_id": self.org_id,
            "tier_used": self._tier_used,
            "sanitized_at": datetime.now(timezone.utc).isoformat(),
            "replacements": [
                {
                    "type": e.data_type,
                    "line": e.line,
                    "original_hash": e.original_hash,
                    "token": e.token,
                    "tier": e.tier
                }
                for e in self.entries
            ]
        }
    
    def set_tiers_used(self, tiers: List[int]) -> None:
        """Set the tiers that were used during sanitization."""
        if tiers:
            self._tier_used = min(tiers)

    def reset(self):
        """Clear all entries"""
        self.entries = []
        self._tier_used = None
