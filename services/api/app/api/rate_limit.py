"""
Rate limit configuration — shared limiter instance and limit constants.
Imported by main.py and all route modules so the same Limiter instance
is used for decorator registration.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address
from app.core.config import settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.RATE_LIMIT_READ],
)

LIMIT_AUTH_LOGIN = "15/minute"
LIMIT_AUTH_REFRESH = "20/minute"
LIMIT_AUTH_REGISTER = "10/minute"
LIMIT_NLI = settings.NLI_RATE_LIMIT
LIMIT_REPORT_CREATE = "20/minute"
LIMIT_COMPLIANCE_READ = "100/minute"
LIMIT_WRITE = settings.RATE_LIMIT_WRITE
LIMIT_READ = settings.RATE_LIMIT_READ
LIMIT_AGENT_UPLOAD = "120/minute"
LIMIT_AGENT_HEARTBEAT = "60/minute"
LIMIT_DISCOVERY_TRIGGER = "30/minute"
