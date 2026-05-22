"""
Redis cache integration with connection pooling.
Used for:
  - Embedding cache  (TTL 24h) — avoid repeat ada-002 API calls
  - Query result cache (TTL 1h) — serve identical searches instantly
"""

import hashlib
import json
import os
from typing import Any, Optional

import redis.asyncio as aioredis
from redis.asyncio import ConnectionPool

from src.handlers.logger import get_logger, log_error, log_info, log_warning

logger = get_logger("integrations.cache")

_pool: Optional[ConnectionPool] = None
_client: Optional[aioredis.Redis] = None


def init_cache(redis_url: str, max_connections: int = 20, password: Optional[str] = None) -> None:
    """
    Initialise the Redis connection pool.
    Called once at startup inside FastAPI lifespan — never per-request.
    """
    global _pool, _client
    _pool = ConnectionPool.from_url(
        redis_url,
        password=password or None,
        max_connections=max_connections,
        decode_responses=True,
    )
    _client = aioredis.Redis(connection_pool=_pool)
    log_info("Redis connection pool initialised | url=%s max_connections=%d", redis_url, max_connections)


def get_cache_client() -> aioredis.Redis:
    if _client is None:
        raise RuntimeError("Cache not initialised. Call init_cache() at startup.")
    return _client


async def cache_get(key: str) -> Optional[Any]:
    """Return parsed JSON value or None on miss / error."""
    try:
        raw = await get_cache_client().get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        log_warning("cache_get failed | key=%s | error=%s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int) -> bool:
    """Serialise value to JSON and store with TTL. Returns True on success."""
    try:
        serialised = json.dumps(value)
        await get_cache_client().setex(key, ttl_seconds, serialised)
        return True
    except Exception as exc:
        log_warning("cache_set failed | key=%s | error=%s", key, exc)
        return False


async def cache_delete(key: str) -> None:
    try:
        await get_cache_client().delete(key)
    except Exception as exc:
        log_warning("cache_delete failed | key=%s | error=%s", key, exc)


async def health_check() -> bool:
    """Return True if Redis responds to PING."""
    try:
        await get_cache_client().ping()
        return True
    except Exception as exc:
        log_warning("Redis health check failed | error=%s", exc)
        return False


# ── Key builders ─────────────────────────────────────────────────────────────

def embedding_cache_key(text: str, model: str) -> str:
    """Deterministic cache key for an embedding request."""
    digest = hashlib.md5(f"{model}:{text}".encode()).hexdigest()
    return f"emb:{digest}"


def query_cache_key(query: str, filters: Optional[dict]) -> str:
    """Deterministic cache key for a search query + filter combination."""
    payload = json.dumps({"q": query.lower().strip(), "f": filters or {}}, sort_keys=True)
    digest = hashlib.md5(payload.encode()).hexdigest()
    return f"search:{digest}"
