"""
Hybrid search orchestrator.

Full pipeline per request:
  1. Redis cache check (hash of query + filters)
  2. Adaptive-K: choose candidate count (3 / 10 / 20)
  3. Embed query with ada-002 (cache-aware)
  4. Parallel BM25 + Qdrant retrieval
  5. RRF fusion
  6. Score-dropoff trim
  7. Cross-encoder rerank
  8. Resolution aggregation (deduplicate fixes)
  9. Write result to Redis (TTL 1h)
 10. Return SearchResponse-compatible dict

Graceful degradation:
  • Qdrant down  → BM25-only mode (retrieval_method = "bm25_only")
  • BM25 missing → vector-only mode (retrieval_method = "vector_only")
  • Both fail    → raises RetrievalError (→ 503 in the API layer)
  • Reranker not loaded → skip reranking, use RRF order
"""

from __future__ import annotations

import time
from typing import Optional

from src.exceptions.custom_exceptions import (
    IndexNotFoundError,
    RetrievalError,
    VectorDBUnavailableError,
)
from src.handlers.logger import get_logger, log_info, log_warning
from src.integrations.cache import cache_get, cache_set, query_cache_key
from src.integrations.embeddings import embed_text
from src.integrations.vector_db import VectorStore
from src.retrieval.adaptive_k import compute_k, trim_by_score_dropoff
from src.retrieval.bm25_retriever import bm25_search, is_bm25_loaded
from src.retrieval.reranker import is_reranker_loaded, rerank
from src.retrieval.resolution_aggregator import aggregate_resolutions
from src.retrieval.rrf_merger import reciprocal_rank_fusion
from src.retrieval.vector_retriever import VectorRetriever

logger = get_logger("retrieval.hybrid_search")


# ── Public entry point ────────────────────────────────────────────────────────


async def hybrid_search(
    query: str,
    vector_store: VectorStore,
    collection: str,
    filters: Optional[dict] = None,
    top_k_override: Optional[int] = None,
    app_config: Optional[dict] = None,
) -> dict:
    """
    Execute the full hybrid retrieval pipeline.

    Parameters
    ----------
    query          : Natural-language incident query.
    vector_store   : Injected VectorStore (Qdrant).
    collection     : Qdrant collection name.
    filters        : Optional metadata filter dict {field: value}.
    top_k_override : If provided, skip Adaptive-K and use this k.
    app_config     : Full app_config.json dict; uses defaults if None.

    Returns
    -------
    dict  Compatible with SearchResponse Pydantic model.

    Raises
    ------
    RetrievalError  if both BM25 and vector search fail.
    """
    cfg = app_config or {}
    retrieval_cfg = cfg.get("RETRIEVAL", {})
    cache_cfg = cfg.get("CACHE", {})

    k_min = retrieval_cfg.get("K_MIN", 3)
    k_default = retrieval_cfg.get("K_DEFAULT", 10)
    k_max = retrieval_cfg.get("K_MAX", 20)
    rrf_k = retrieval_cfg.get("RRF_K", 60)
    dropoff_threshold = retrieval_cfg.get("SCORE_DROPOFF_THRESHOLD", 0.15)
    dedup_threshold = retrieval_cfg.get("RESOLUTION_DEDUP_THRESHOLD", 0.95)
    top_k_final = retrieval_cfg.get("TOP_K_FINAL", 10)
    cache_ttl = cache_cfg.get("QUERY_RESULT_TTL_SECONDS", 3600)

    start_ts = time.monotonic()

    # ── 1. Redis cache check ──────────────────────────────────────────────────
    cache_key = query_cache_key(query, filters)
    cached_result = await cache_get(cache_key)
    if cached_result is not None:
        cached_result["cached"] = True
        log_info("Cache HIT | query='%s'", query[:60])
        return cached_result

    # ── 2. Adaptive-K ─────────────────────────────────────────────────────────
    k = top_k_override if top_k_override is not None else compute_k(
        query, k_min=k_min, k_default=k_default, k_max=k_max
    )

    # ── 3. Embed query ────────────────────────────────────────────────────────
    query_vector = await embed_text(query)

    # ── 4. BM25 + Vector retrieval (independent, not parallel here since
    #       BM25 is synchronous CPU-only and very fast < 1ms) ─────────────────
    bm25_results: list[dict] = []
    vector_results: list[dict] = []
    retrieval_method = "hybrid"

    if is_bm25_loaded():
        try:
            bm25_results = bm25_search(query, top_k=k)
        except IndexNotFoundError:
            log_warning("BM25 index not found — skipping keyword leg")
        except Exception as exc:
            log_warning("BM25 retrieval error | error=%s", exc)
    else:
        log_warning("BM25 not loaded — skipping keyword leg")

    try:
        vector_retriever = VectorRetriever(vector_store, collection)
        vector_results = await vector_retriever.search(
            query_vector=query_vector,
            top_k=k,
            filters=filters,
        )
    except VectorDBUnavailableError as exc:
        log_warning("Qdrant unavailable | error=%s — falling back to BM25-only", exc)
        retrieval_method = "bm25_only"
    except Exception as exc:
        log_warning("Vector retrieval error | error=%s — falling back to BM25-only", exc)
        retrieval_method = "bm25_only"

    if not bm25_results and not vector_results:
        raise RetrievalError(
            "Both BM25 and vector search returned no results.",
            details={"query": query, "filters": filters},
        )

    if not vector_results:
        retrieval_method = "bm25_only"
    elif not bm25_results:
        retrieval_method = "vector_only"

    # ── 5. RRF fusion ─────────────────────────────────────────────────────────
    merged = reciprocal_rank_fusion(bm25_results, vector_results, k=rrf_k)
    total_found = len(merged)

    # ── 6. Trim score dropoff ─────────────────────────────────────────────────
    trimmed = trim_by_score_dropoff(merged, threshold=dropoff_threshold)

    # ── 7. Cross-encoder rerank ───────────────────────────────────────────────
    if is_reranker_loaded():
        reranked = rerank(query, trimmed)
    else:
        from src.retrieval.reranker import _add_fallback_scores
        _add_fallback_scores(trimmed)
        reranked = trimmed

    # Take final top-k
    final = reranked[:top_k_final]

    # ── 8. Resolution aggregation ─────────────────────────────────────────────
    resolution_options = await aggregate_resolutions(final, dedup_threshold=dedup_threshold)

    # ── 9. Build response dict ────────────────────────────────────────────────
    latency_ms = round((time.monotonic() - start_ts) * 1000, 1)

    result = {
        "query": query,
        "total_found": total_found,
        "results": [_build_incident_response(r) for r in final],
        "resolution_options": resolution_options,
        "adaptive_k_used": k,
        "retrieval_method": retrieval_method,
        "cached": False,
        "latency_ms": latency_ms,
    }

    # ── 10. Write to Redis cache ───────────────────────────────────────────────
    await cache_set(cache_key, result, cache_ttl)

    log_info(
        "Hybrid search | query='%s' k=%d method=%s results=%d latency_ms=%.1f",
        query[:60],
        k,
        retrieval_method,
        len(final),
        latency_ms,
    )
    return result


# ── Private helpers ───────────────────────────────────────────────────────────


def _build_incident_response(candidate: dict) -> dict:
    """Convert a pipeline candidate dict to an IncidentResponse-compatible dict."""
    payload = candidate.get("payload", {})
    similarity = candidate.get("similarity_score", _rrf_to_similarity(candidate.get("score", 0.0)))

    return {
        "incident_id": payload.get("incident_id", str(candidate.get("id", ""))),
        "ticket_id": payload.get("ticket_id") or None,
        "title": payload.get("title") or None,
        "category": payload.get("category") or None,
        "description": payload.get("description", ""),
        "resolution_notes": payload.get("resolution_notes") or None,
        "assigned_to": payload.get("assigned_to") or None,
        "similarity_score": round(max(0.0, min(1.0, similarity)), 4),
        "occurrence_count": 1,
    }


def _rrf_to_similarity(rrf_score: float) -> float:
    """
    Normalise an RRF score to [0, 1].
    Maximum possible RRF score when ranked #1 in both lists: 2 / (60+1) ≈ 0.0328.
    """
    max_rrf = 2.0 / 61.0
    return min(1.0, rrf_score / max_rrf) if max_rrf > 0 else 0.0
