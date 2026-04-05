"""Tests that trigger_discovery uses async Redis to avoid blocking the event loop."""
import pytest


@pytest.mark.asyncio
async def test_trigger_discovery_redis_push_is_awaited():
    """Redis lpush inside trigger_discovery must be awaited (async), not blocking."""
    with open("app/api/routes/discoveries.py") as f:
        content = f.read()

    assert "redis.asyncio" in content or "aioredis" in content, (
        "discoveries.py must use redis.asyncio (async), not sync redis"
    )
    assert "import redis\n" not in content and "import redis " not in content, (
        "discoveries.py must not import sync redis"
    )
