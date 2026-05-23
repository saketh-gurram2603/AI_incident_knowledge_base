"""
Health check endpoints.
  GET /health        — liveness  (is the process alive?)
  GET /health/ready  — readiness (can we accept traffic? checks all dependencies)
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.integrations.cache import health_check as redis_health
from src.integrations.database import health_check as postgres_health
from src.handlers.logger import get_logger

logger = get_logger("api.health")

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness probe")
async def liveness():
    """Kubernetes liveness probe — returns 200 if the process is running."""
    return {"status": "alive", "service": "incident-kb-assistant"}


@router.get("/health/ready", summary="Readiness probe")
async def readiness():
    """
    Kubernetes readiness probe.
    Checks Qdrant, Redis, and Postgres connectivity.
    Returns 503 if any dependency is unavailable.
    """

    checks: dict[str, bool] = {}

    # Redis
    checks["redis"] = await redis_health()

    # Postgres
    checks["postgres"] = await postgres_health()

    # Qdrant — imported from app state via module-level reference
    try:
        from src.integrations import _qdrant_store  # set at startup
        checks["qdrant"] = await _qdrant_store.health_check()
    except Exception:
        checks["qdrant"] = False

    all_healthy = all(checks.values())
    status_code = 200 if all_healthy else 503

    logger.info("Readiness check | %s", checks)

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if all_healthy else "degraded",
            "checks": {k: "ok" if v else "fail" for k, v in checks.items()},
        },
    )
