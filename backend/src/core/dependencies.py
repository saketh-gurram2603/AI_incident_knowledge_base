"""
FastAPI dependency injection — mirrors Synapt-PersonalizedRAG-API pattern.
All services injected via Depends() so endpoints are testable (mock-able).
"""

from fastapi import Request

from src.integrations.vector_db import VectorStore
from src.integrations.cache import get_cache_client
import redis.asyncio as aioredis


def get_app_config(request: Request) -> dict:
    """Inject static app config (from app_config.json)."""
    return request.app.state.app_config


def get_env_config(request: Request) -> dict:
    """Inject environment config (from config.json[env])."""
    return request.app.state.env_config


def get_vector_store(request: Request) -> VectorStore:
    """Inject the VectorStore implementation (QdrantVectorStore)."""
    return request.app.state.vector_store


def get_redis(request: Request) -> aioredis.Redis:
    """Inject the Redis client."""
    return get_cache_client()
