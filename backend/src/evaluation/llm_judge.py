"""
LLM-as-Judge evaluation using DeepEval.

Metrics computed:
  - Faithfulness          — does the answer stay grounded in the retrieved context?
  - Answer Relevancy      — does the answer address the question?
  - Contextual Precision  — are the retrieved docs actually relevant to the question?

All three metrics call OpenAI under the hood.  Results are returned as plain
dicts so the runner can serialise them to Postgres without a DeepEval dependency
in other modules.

If DeepEval or OpenAI is unavailable, each metric returns score=0.0 with
reason="unavailable" so the eval pipeline degrades gracefully.
"""

from __future__ import annotations

import os
from typing import Optional

from src.handlers.logger import get_logger, log_info, log_warning

logger = get_logger("evaluation.llm_judge")


def _get_openai_key() -> str:
    return os.getenv("OPENAI_API_KEY", "")


# ── Core evaluation function ──────────────────────────────────────────────────


async def evaluate_with_llm_judge(
    query: str,
    actual_output: str,
    expected_output: str,
    retrieval_context: list[str],
    faithfulness_threshold: float = 0.70,
    relevancy_threshold: float = 0.75,
    contextual_precision_threshold: float = 0.65,
) -> dict:
    """
    Run DeepEval LLM-as-Judge metrics for a single test case.

    Returns a dict:
    {
        "faithfulness":         {"score": float, "reason": str, "passed": bool},
        "answer_relevancy":     {"score": float, "reason": str, "passed": bool},
        "contextual_precision": {"score": float, "reason": str, "passed": bool},
    }
    """
    api_key = _get_openai_key()
    if not api_key:
        log_warning("OPENAI_API_KEY not set — skipping LLM judge")
        return _unavailable_result()

    try:
        from deepeval import evaluate as deepeval_evaluate
        from deepeval.metrics import (
            AnswerRelevancyMetric,
            ContextualPrecisionMetric,
            FaithfulnessMetric,
        )
        from deepeval.test_case import LLMTestCase
    except ImportError:
        log_warning("deepeval not installed — skipping LLM judge")
        return _unavailable_result()

    try:
        test_case = LLMTestCase(
            input=query,
            actual_output=actual_output,
            expected_output=expected_output,
            retrieval_context=retrieval_context,
        )

        faith_metric = FaithfulnessMetric(
            threshold=faithfulness_threshold,
            model="gpt-4o-mini",
            include_reason=True,
        )
        relevancy_metric = AnswerRelevancyMetric(
            threshold=relevancy_threshold,
            model="gpt-4o-mini",
            include_reason=True,
        )
        precision_metric = ContextualPrecisionMetric(
            threshold=contextual_precision_threshold,
            model="gpt-4o-mini",
            include_reason=True,
        )

        # Measure each metric (DeepEval's measure() is synchronous)
        import asyncio
        loop = asyncio.get_event_loop()

        await loop.run_in_executor(None, lambda: faith_metric.measure(test_case))
        await loop.run_in_executor(None, lambda: relevancy_metric.measure(test_case))
        await loop.run_in_executor(None, lambda: precision_metric.measure(test_case))

        result = {
            "faithfulness": {
                "score": round(float(faith_metric.score or 0.0), 4),
                "reason": faith_metric.reason or "",
                "passed": bool(faith_metric.is_successful()),
            },
            "answer_relevancy": {
                "score": round(float(relevancy_metric.score or 0.0), 4),
                "reason": relevancy_metric.reason or "",
                "passed": bool(relevancy_metric.is_successful()),
            },
            "contextual_precision": {
                "score": round(float(precision_metric.score or 0.0), 4),
                "reason": precision_metric.reason or "",
                "passed": bool(precision_metric.is_successful()),
            },
        }

        log_info(
            "LLM judge | faith=%.2f relevancy=%.2f precision=%.2f",
            result["faithfulness"]["score"],
            result["answer_relevancy"]["score"],
            result["contextual_precision"]["score"],
        )
        return result

    except Exception as exc:
        log_warning("LLM judge evaluation failed | error=%s", exc)
        return _unavailable_result(reason=str(exc))


# ── Batch evaluation ──────────────────────────────────────────────────────────


async def batch_evaluate(
    test_cases: list[dict],
    faithfulness_threshold: float = 0.70,
    relevancy_threshold: float = 0.75,
    contextual_precision_threshold: float = 0.65,
) -> list[dict]:
    """
    Run LLM judge over a batch of test cases.

    Each test_case dict must have:
        query, actual_output, expected_output, retrieval_context (list[str])

    Returns list of result dicts (same order as input).
    """
    results = []
    for i, tc in enumerate(test_cases):
        log_info("LLM judge batch | case %d/%d", i + 1, len(test_cases))
        result = await evaluate_with_llm_judge(
            query=tc.get("query", ""),
            actual_output=tc.get("actual_output", ""),
            expected_output=tc.get("expected_output", ""),
            retrieval_context=tc.get("retrieval_context", []),
            faithfulness_threshold=faithfulness_threshold,
            relevancy_threshold=relevancy_threshold,
            contextual_precision_threshold=contextual_precision_threshold,
        )
        results.append(result)
    return results


def aggregate_llm_scores(judge_results: list[dict]) -> dict[str, float]:
    """
    Average each LLM-judge metric across all test cases.

    Returns:
        {
            "avg_faithfulness":         float,
            "avg_answer_relevancy":     float,
            "avg_contextual_precision": float,
        }
    """
    if not judge_results:
        return {
            "avg_faithfulness": 0.0,
            "avg_answer_relevancy": 0.0,
            "avg_contextual_precision": 0.0,
        }

    def _avg(key: str) -> float:
        scores = [r[key]["score"] for r in judge_results if key in r]
        return round(sum(scores) / len(scores), 4) if scores else 0.0

    return {
        "avg_faithfulness": _avg("faithfulness"),
        "avg_answer_relevancy": _avg("answer_relevancy"),
        "avg_contextual_precision": _avg("contextual_precision"),
    }


# ── Private helpers ───────────────────────────────────────────────────────────


def _unavailable_result(reason: str = "unavailable") -> dict:
    stub = {"score": 0.0, "reason": reason, "passed": False}
    return {
        "faithfulness": stub.copy(),
        "answer_relevancy": stub.copy(),
        "contextual_precision": stub.copy(),
    }
