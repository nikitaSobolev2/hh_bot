"""Shared async Redis client factory.

All services that need a Redis connection should use ``create_async_redis``
from this module.  This ensures consistent URL, decode_responses, and
connection pool settings across the application.
"""

from __future__ import annotations


def create_async_redis():
    """Create an async Redis client from application settings.

    Returns a ``redis.asyncio.Redis`` instance with:
    - ``decode_responses=True`` — all keys and values are native Python strings
    - URL from ``settings.redis_url``

    Callers are responsible for closing the connection when done.
    """
    import redis.asyncio as aioredis

    from src.config import settings

    return aioredis.Redis.from_url(settings.redis_url, decode_responses=True)
