"""
Evaluation runner — orchestrates the full eval pipeline and persists results.

Pipeline per test case:
  1. Run hybrid_search for the query
  2. Compute IR metrics vs ground-truth relevant IDs
  3. (Optional) Run LLM judge against the retrieved context + expected answer

Aggregate across all test cases, persist to Postgres, return EvalRunResult.

ORM model EvalRunDB is defined here so main.py can import it before
create_tables() to ensure the table exists at startup.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.evaluation.ir_metrics import compute_all_metrics
from src.evaluation.llm_judge import aggregate_llm_scores, batch_evaluate
from src.handlers.logger import get_logger, log_error, log_info, log_warning
from src.integrations.database import Base, get_session
from src.integrations.vector_db import VectorStore

logger = get_logger("evaluation.runner")

# Default dataset location (relative to this file's package)
_DEFAULT_DATASET = (
    Path(__file__).parent / "ground_truth" / "dataset.json"
)


# ── ORM model ─────────────────────────────────────────────────────────────────


class EvalRunDB(Base):
    """Postgres table for evaluation run results."""

    __tablename__ = "eval_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    num_test_cases: Mapped[int] = mapped_column(Integer, nullable=False)
    ndcg_at_k: Mapped[float] = mapped_column(nullable=False, default=0.0)
    map_at_k: Mapped[float] = mapped_column(nullable=False, default=0.0)
    recall_at_k: Mapped[float] = mapped_column(nullable=False, default=0.0)
    precision_at_k: Mapped[float] = mapped_column(nullable=False, default=0.0)
    avg_faithfulness: Mapped[float] = mapped_column(nullable=False, default=0.0)
    avg_answer_relevancy: Mapped[float] = mapped_column(nullable=False, default=0.0)
    avg_contextual_precision: Mapped[float] = mapped_column(nullable=False, default=0.0)
    overall_passed: Mapped[bool] = mapped_column(nullable=False, default=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# ── Main runner ───────────────────────────────────────────────────────────────


async def run_evaluation(
    vector_store: VectorStore,
    collection: str,
    app_config: dict,
    dataset_path: Optional[str] = None,
    run_llm_judge: bool = True,
    run_ir_metrics: bool = True,
) -> dict:
    """
    Execute the full evaluation pipeline over the ground truth dataset.

    Args:
        vector_store:   Injected QdrantVectorStore.
        collection:     Qdrant collection name.
        app_config:     Loaded app_config.json dict.
        dataset_path:   Override path to ground truth JSON. Uses built-in if None.
        run_llm_judge:  Whether to run DeepEval LLM-as-Judge metrics.
        run_ir_metrics: Whether to run classical IR metrics.

    Returns a dict matching EvalResult schema.
    """
    import time
    start_ts = time.monotonic()

    run_id = f"EVAL-{uuid.uuid4().hex[:8].upper()}"
    log_info("Evaluation run started | run_id=%s", run_id)

    # ── Load dataset ──────────────────────────────────────────────────────────
    dataset = _load_dataset(dataset_path)
    if not dataset:
        raise ValueError("Ground truth dataset is empty or could not be loaded.")

    eval_cfg = app_config.get("EVALUATION", {})
    k = eval_cfg.get("NDCG_K", 10)
    faith_threshold = eval_cfg.get("FAITHFULNESS_THRESHOLD", 0.70)
    relevancy_threshold = eval_cfg.get("RELEVANCY_THRESHOLD", 0.75)
    precision_threshold = eval_cfg.get("CONTEXTUAL_PRECISION_THRESHOLD", 0.65)

    # ── Run retrieval for each test case ──────────────────────────────────────
    from src.retrieval.hybrid_search import hybrid_search

    ir_scores_list: list[dict] = []
    llm_cases: list[dict] = []

    for i, tc in enumerate(dataset):
        query = tc.get("query", "")
        relevant_ids = tc.get("relevant_incident_ids", [])
        expected_answer = tc.get("expected_answer", "")

        log_info("Eval case %d/%d | query='%s'", i + 1, len(dataset), query[:60])

        # Retrieval
        try:
            search_result = await hybrid_search(
                query=query,
                vector_store=vector_store,
                collection=collection,
                app_config=app_config,
            )
            retrieved = search_result.get("results", [])
            retrieved_ids = [r.get("incident_id", r.get("id", "")) for r in retrieved]
            context_texts = [
                f"{r.get('title', '')}: {r.get('resolution_notes', '')}"
                for r in retrieved[:5]
            ]
            actual_output = retrieved[0].get("resolution_notes", "") if retrieved else ""
        except Exception as exc:
            log_warning("Retrieval failed for case %d | error=%s", i + 1, exc)
            retrieved_ids = []
            context_texts = []
            actual_output = ""

        # IR metrics
        if run_ir_metrics and relevant_ids:
            scores = compute_all_metrics(retrieved_ids, relevant_ids, k=k)
            ir_scores_list.append(scores)

        # Prepare LLM judge case
        if run_llm_judge and expected_answer:
            llm_cases.append({
                "query": query,
                "actual_output": actual_output,
                "expected_output": expected_answer,
                "retrieval_context": context_texts,
            })

    # ── Aggregate IR metrics ──────────────────────────────────────────────────
    avg_ir = _average_ir_scores(ir_scores_list)

    # ── Run LLM judge ─────────────────────────────────────────────────────────
    avg_llm: dict[str, float] = {
        "avg_faithfulness": 0.0,
        "avg_answer_relevancy": 0.0,
        "avg_contextual_precision": 0.0,
    }
    if run_llm_judge and llm_cases:
        judge_results = await batch_evaluate(
            llm_cases,
            faithfulness_threshold=faith_threshold,
            relevancy_threshold=relevancy_threshold,
            contextual_precision_threshold=precision_threshold,
        )
        avg_llm = aggregate_llm_scores(judge_results)

    # ── Build MetricScore list ────────────────────────────────────────────────
    thresholds = {
        "ndcg_at_k": 0.60,
        "map_at_k": 0.55,
        "recall_at_k": 0.60,
        "precision_at_k": 0.50,
        "avg_faithfulness": faith_threshold,
        "avg_answer_relevancy": relevancy_threshold,
        "avg_contextual_precision": precision_threshold,
    }

    all_scores = {**avg_ir, **avg_llm}
    metrics = [
        {
            "name": name,
            "score": round(score, 4),
            "threshold": thresholds.get(name, 0.50),
            "passed": score >= thresholds.get(name, 0.50),
        }
        for name, score in all_scores.items()
        if (name.startswith("avg_") and run_llm_judge)
        or (not name.startswith("avg_") and run_ir_metrics)
    ]

    overall_passed = all(m["passed"] for m in metrics)
    latency_ms = (time.monotonic() - start_ts) * 1000
    timestamp = datetime.now(timezone.utc).isoformat()

    log_info(
        "Eval run complete | run_id=%s overall_passed=%s latency=%.0fms",
        run_id, overall_passed, latency_ms,
    )

    # ── Persist to Postgres ───────────────────────────────────────────────────
    await _save_eval_run(
        run_id=run_id,
        num_test_cases=len(dataset),
        avg_ir=avg_ir,
        avg_llm=avg_llm,
        overall_passed=overall_passed,
        metrics=metrics,
    )

    return {
        "run_id": run_id,
        "metrics": metrics,
        "overall_passed": overall_passed,
        "num_test_cases": len(dataset),
        "latency_ms": round(latency_ms, 1),
        "timestamp": timestamp,
    }


async def get_latest_eval_run() -> Optional[dict]:
    """Fetch the most recent evaluation run from Postgres."""
    from sqlalchemy import select

    try:
        async with get_session() as session:
            stmt = (
                select(EvalRunDB)
                .order_by(EvalRunDB.created_at.desc())
                .limit(1)
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return _row_to_dict(row)
    except Exception as exc:
        log_error("get_latest_eval_run failed | error=%s", exc)
        return None


# ── Private helpers ───────────────────────────────────────────────────────────


def _load_dataset(path: Optional[str] = None) -> list[dict]:
    """Load ground truth dataset from JSON file."""
    target = Path(path) if path else _DEFAULT_DATASET
    if not target.exists():
        log_warning("Ground truth dataset not found at %s", target)
        return []
    try:
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
        log_info("Loaded %d test cases from %s", len(data), target)
        return data
    except Exception as exc:
        log_error("Failed to load dataset | path=%s error=%s", target, exc)
        return []


def _average_ir_scores(scores_list: list[dict]) -> dict[str, float]:
    """Average IR metric dicts across test cases."""
    if not scores_list:
        return {
            "ndcg_at_k": 0.0,
            "map_at_k": 0.0,
            "recall_at_k": 0.0,
            "precision_at_k": 0.0,
        }
    keys = ["ndcg_at_k", "map_at_k", "recall_at_k", "precision_at_k"]
    n = len(scores_list)
    return {
        key: round(sum(s.get(key, 0.0) for s in scores_list) / n, 4)
        for key in keys
    }


async def _save_eval_run(
    run_id: str,
    num_test_cases: int,
    avg_ir: dict,
    avg_llm: dict,
    overall_passed: bool,
    metrics: list[dict],
) -> None:
    """Persist eval run to Postgres. Logs error on failure, never raises."""
    try:
        async with get_session() as session:
            row = EvalRunDB(
                run_id=run_id,
                num_test_cases=num_test_cases,
                ndcg_at_k=avg_ir.get("ndcg_at_k", 0.0),
                map_at_k=avg_ir.get("map_at_k", 0.0),
                recall_at_k=avg_ir.get("recall_at_k", 0.0),
                precision_at_k=avg_ir.get("precision_at_k", 0.0),
                avg_faithfulness=avg_llm.get("avg_faithfulness", 0.0),
                avg_answer_relevancy=avg_llm.get("avg_answer_relevancy", 0.0),
                avg_contextual_precision=avg_llm.get("avg_contextual_precision", 0.0),
                overall_passed=overall_passed,
                details_json=json.dumps(metrics),
            )
            session.add(row)
        log_info("Eval run persisted | run_id=%s", run_id)
    except Exception as exc:
        log_error("Failed to persist eval run | run_id=%s error=%s", run_id, exc)


def _row_to_dict(row: EvalRunDB) -> dict:
    """Convert ORM row to serialisable dict."""
    metrics = []
    if row.details_json:
        try:
            metrics = json.loads(row.details_json)
        except Exception:
            pass
    return {
        "run_id": row.run_id,
        "metrics": metrics,
        "overall_passed": row.overall_passed,
        "num_test_cases": row.num_test_cases,
        "timestamp": row.created_at.isoformat() if row.created_at else "",
    }
