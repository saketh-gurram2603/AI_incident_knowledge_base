"""
Resolution aggregator.

After reranking, multiple retrieved incidents may share the same (or very
similar) resolution.  This module:

  1. Embeds each incident's resolution_notes.
  2. Runs greedy cosine-similarity clustering (threshold 0.95 by default).
  3. For each cluster, records:
       - resolution_text : representative resolution (first in cluster)
       - occurrence_count: how many past incidents used this fix
       - avg_similarity  : mean reranked similarity score of the cluster
       - source_incident_ids: incident IDs that belong to the cluster
  4. Sorts clusters by  occurrence_count × avg_similarity  (most-proven first).

Why greedy clustering?
  • O(n²) cosine comparisons is fine for n ≤ 20 (trimmed candidate set).
  • Greedy gives stable, deterministic results unlike k-means.
  • Threshold 0.95 is strict enough to avoid false merges.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from src.handlers.logger import get_logger, log_info
from src.integrations.embeddings import embed_batch

logger = get_logger("retrieval.resolution_aggregator")


# ── Public API ─────────────────────────────────────────────────────────────────


async def aggregate_resolutions(
    reranked: list[dict],
    dedup_threshold: float = 0.95,
) -> list[dict]:
    """
    Cluster and deduplicate resolutions from a reranked incident list.

    Parameters
    ----------
    reranked         : Output of the cross-encoder reranker (list of candidate dicts).
    dedup_threshold  : Cosine similarity threshold for merging two resolutions.

    Returns
    -------
    list[dict]  Each item matches the ResolutionOption schema:
        {resolution_text, occurrence_count, avg_similarity, source_incident_ids}
    """
    if not reranked:
        return []

    # Extract resolution notes from each candidate's payload
    notes: list[str] = [
        c.get("payload", {}).get("resolution_notes", "") or ""
        for c in reranked
    ]

    # Embed all resolution notes in one batched call (cache-aware)
    vectors: list[list[float]] = await embed_batch(notes)

    # Greedy cosine clustering
    clusters: list[list[int]] = _greedy_cluster(vectors, dedup_threshold)

    # Build ResolutionOption dicts
    resolution_options: list[dict] = []
    for cluster_indices in clusters:
        # Representative: first member (highest rerank score since list is sorted)
        rep_idx = cluster_indices[0]
        resolution_text = notes[rep_idx]

        if not resolution_text.strip():
            continue  # Skip empty resolutions

        occurrence_count = len(cluster_indices)
        avg_similarity = _mean_similarity(reranked, cluster_indices)
        source_ids = [reranked[i]["id"] for i in cluster_indices]

        resolution_options.append(
            {
                "resolution_text": resolution_text,
                "occurrence_count": occurrence_count,
                "avg_similarity": round(avg_similarity, 4),
                "source_incident_ids": source_ids,
            }
        )

    # Sort: most-proven × highest-confidence first
    resolution_options.sort(
        key=lambda x: x["occurrence_count"] * x["avg_similarity"],
        reverse=True,
    )

    log_info(
        "Resolution aggregation | incidents=%d clusters=%d",
        len(reranked),
        len(resolution_options),
    )
    return resolution_options


# ── Private helpers ───────────────────────────────────────────────────────────


def _greedy_cluster(
    vectors: list[list[float]],
    threshold: float,
) -> list[list[int]]:
    """
    Greedy cosine-similarity clustering.

    Iterates through vectors in order; each unassigned vector starts a new
    cluster and absorbs any subsequent unassigned vector with cosine ≥ threshold.

    Returns
    -------
    list[list[int]]  Cluster membership by original index.
    """
    n = len(vectors)
    assigned = [False] * n
    clusters: list[list[int]] = []

    for i in range(n):
        if assigned[i]:
            continue
        cluster = [i]
        assigned[i] = True
        for j in range(i + 1, n):
            if not assigned[j]:
                sim = _cosine_similarity(vectors[i], vectors[j])
                if sim >= threshold:
                    cluster.append(j)
                    assigned[j] = True
        clusters.append(cluster)

    return clusters


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors using numpy."""
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(va)
    norm_b = np.linalg.norm(vb)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (norm_a * norm_b))


def _mean_similarity(candidates: list[dict], indices: list[int]) -> float:
    """
    Mean similarity_score across cluster members.
    Falls back to a default (0.5) if the field is absent.
    """
    scores = [
        candidates[i].get("similarity_score", candidates[i].get("score", 0.5))
        for i in indices
    ]
    return sum(scores) / len(scores) if scores else 0.0
