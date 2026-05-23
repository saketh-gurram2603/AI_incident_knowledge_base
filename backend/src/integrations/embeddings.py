"""
Embedding integration.
Primary  : OpenAI text-embedding-ada-002 (batched, cached in Redis)
Fallback : sentence-transformers/all-MiniLM-L6-v2 (local, loaded at startup)
"""

import asyncio
import os
from typing import Optional

from openai import AsyncOpenAI

from src.integrations.cache import cache_get, cache_set, embedding_cache_key
from src.handlers.logger import get_logger, log_error, log_info, log_warning

# sentence_transformers / torch are imported lazily inside init_embeddings()
# and _embed_local() so a torch/torchvision version mismatch never crashes
# the application at startup — it only surfaces if the local fallback is used.

logger = get_logger("integrations.embeddings")

# ── Module-level state (initialised at startup) ───────────────────────────────
_openai_client: Optional[AsyncOpenAI] = None
_local_model = None   # SentenceTransformer — lazy-loaded
_embedding_model_name: str = "text-embedding-ada-002"
_fallback_model_name: str = "all-MiniLM-L6-v2"
_embedding_ttl: int = 86400
_openai_available: bool = True   # toggled by circuit breaker


def init_embeddings(
    openai_api_key: str,
    embedding_model: str = "text-embedding-ada-002",
    fallback_model: str = "all-MiniLM-L6-v2",
    embedding_ttl: int = 86400,
) -> None:
    """Load local fallback model and configure OpenAI client. Called at startup."""
    global _openai_client, _local_model, _embedding_model_name, _fallback_model_name, _embedding_ttl

    _embedding_model_name = embedding_model
    _fallback_model_name = fallback_model
    _embedding_ttl = embedding_ttl

    _openai_client = AsyncOpenAI(api_key=openai_api_key)
    log_info("OpenAI embedding client initialised | model=%s", embedding_model)

    log_info("Loading local fallback embedding model '%s' ...", fallback_model)
    try:
        from sentence_transformers import SentenceTransformer  # lazy import
        _local_model = SentenceTransformer(fallback_model)
        log_info("Local embedding model '%s' loaded successfully", fallback_model)
    except Exception as exc:
        log_warning(
            "Local embedding model '%s' could not be loaded (torch/torchvision issue?) "
            "— will rely on OpenAI only | error=%s",
            fallback_model, exc,
        )
        _local_model = None


async def embed_text(text: str) -> list[float]:
    """
    Embed a single text string.
    1. Check Redis cache
    2. Try OpenAI ada-002
    3. Fall back to local MiniLM
    """
    cache_key = embedding_cache_key(text, _embedding_model_name)

    # ── Cache hit ─────────────────────────────────────────────────────────────
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached

    # ── OpenAI primary ────────────────────────────────────────────────────────
    if _openai_available and _openai_client:
        try:
            response = await asyncio.wait_for(
                _openai_client.embeddings.create(
                    model=_embedding_model_name,
                    input=text,
                ),
                timeout=30.0,
            )
            vector = response.data[0].embedding
            await cache_set(cache_key, vector, _embedding_ttl)
            return vector
        except Exception as exc:
            log_warning("OpenAI embed failed, falling back to local | error=%s", exc)

    # ── Local fallback ────────────────────────────────────────────────────────
    return _embed_local(text)


async def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts in one OpenAI API call (more efficient than one-by-one).
    Falls back to local model per-text if OpenAI fails.
    """
    if not texts:
        return []

    # Check cache for all items first
    results: list[list[float] | None] = []
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []

    for i, text in enumerate(texts):
        cached = await cache_get(embedding_cache_key(text, _embedding_model_name))
        if cached is not None:
            results.append(cached)
        else:
            results.append(None)
            uncached_indices.append(i)
            uncached_texts.append(text)

    if not uncached_texts:
        return results  # type: ignore[return-value]

    # Batch call OpenAI for uncached texts
    if _openai_available and _openai_client and uncached_texts:
        try:
            response = await asyncio.wait_for(
                _openai_client.embeddings.create(
                    model=_embedding_model_name,
                    input=uncached_texts,
                ),
                timeout=60.0,
            )
            for idx, emb_data in zip(uncached_indices, response.data):
                vector = emb_data.embedding
                results[idx] = vector
                await cache_set(
                    embedding_cache_key(texts[idx], _embedding_model_name),
                    vector,
                    _embedding_ttl,
                )
            return results  # type: ignore[return-value]
        except Exception as exc:
            log_warning("OpenAI batch embed failed, using local fallback | error=%s", exc)

    # Fallback: embed uncached texts locally
    for i in uncached_indices:
        results[i] = _embed_local(texts[i])

    return results  # type: ignore[return-value]


def _embed_local(text: str) -> list[float]:
    """Synchronous local embedding via sentence-transformers."""
    if _local_model is None:
        raise RuntimeError(
            "Local embedding model is unavailable (load failed at startup or not initialised). "
            "Check that torch and torchvision are compatible versions."
        )
    vector = _local_model.encode(text, normalize_embeddings=True).tolist()
    log_info("Used local MiniLM embedding for text (len=%d)", len(text))
    return vector
