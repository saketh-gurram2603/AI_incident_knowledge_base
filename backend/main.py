"""
main.py — Application entry point.
Mirrors Synapt-PersonalizedRAG-API structure:
  1. Parse CLI environment argument
  2. Load configs (app_config.json + config.json[env] + env secrets)
  3. Initialise all services in lifespan (models, DB, cache, vector store)
  4. Register routers and exception handlers
  5. Start Uvicorn

Usage:
  python main.py development
  python main.py docker
  python main.py production
"""

import os
import sys
import uvicorn
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ── Config loading ────────────────────────────────────────────────────────────
from src.core.config import (
    load_app_config,
    load_env_config,
    load_environment,
    require_env,
    get_env,
)

# ── Logging ───────────────────────────────────────────────────────────────────
from src.handlers.logger import init_loggers, log_info, log_error

# ── Exception handlers ────────────────────────────────────────────────────────
from src.exceptions.exception_handler import register_exception_handlers

# ── Integrations ──────────────────────────────────────────────────────────────
from src.integrations.vector_db import QdrantVectorStore
from src.integrations.cache import init_cache
from src.integrations.database import init_database, create_tables
from src.integrations.embeddings import init_embeddings
from src.integrations.llm import init_llm
import src.integrations as integrations_pkg

# ── ORM models (must be imported before create_tables) ────────────────────────
from src.agents.l3_specialist import EscalationTicketDB  # noqa: F401 — registers table

# ── Agent graph ───────────────────────────────────────────────────────────────
from src.agents.graph import build_triage_graph

# ── API routers ───────────────────────────────────────────────────────────────
from src.api.health import router as health_router
from src.api.ingestion import router as ingestion_router
from src.api.search import router as search_router
from src.api.triage import router as triage_router
from src.api.evaluation import router as evaluation_router

# ─────────────────────────────────────────────────────────────────────────────
# Environment
# ─────────────────────────────────────────────────────────────────────────────
_VALID_ENVS = {"development", "docker", "production"}
environment = sys.argv[1] if len(sys.argv) > 1 else "development"
if environment not in _VALID_ENVS:
    print(f"[WARN] Unknown environment '{environment}' — defaulting to 'development'")
    environment = "development"

# Load configs immediately (before lifespan so they're available at import time)
app_config = load_app_config()
env_config = load_env_config(environment)
load_environment(environment, env_config)

# Initialise loggers as soon as env is loaded
_log_cfg = app_config["LOGGING"]
init_loggers(
    log_dir=_log_cfg["LOG_DIR"],
    max_bytes=_log_cfg["MAX_BYTES"],
    backup_count=_log_cfg["BACKUP_COUNT"],
    log_level=env_config.get("log_level", "INFO"),
)

log_info("=" * 60)
log_info("Starting %s | env=%s", app_config["APP_NAME"], environment)
log_info("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Lifespan — load ALL heavy resources at startup, never on first request
# ─────────────────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialise all services. Shutdown: clean up."""
    log_info("Lifespan startup — initialising services ...")

    # ── Cache (Redis) ─────────────────────────────────────────────────────────
    redis_password = get_env("REDIS_PASSWORD", "")
    init_cache(
        redis_url=env_config["redis_url"],
        max_connections=app_config["CACHE"]["MAX_CONNECTIONS"],
        password=redis_password or None,
    )

    # ── Database (Postgres) ───────────────────────────────────────────────────
    init_database(
        host=env_config["postgres_host"],
        port=env_config["postgres_port"],
        db=env_config["postgres_db"],
        user=require_env("POSTGRES_USER"),
        password=require_env("POSTGRES_PASSWORD"),
        pool_size=app_config["DATABASE"]["POOL_SIZE"],
        max_overflow=app_config["DATABASE"]["MAX_OVERFLOW"],
        pool_recycle=app_config["DATABASE"]["POOL_RECYCLE_SECONDS"],
    )
    await create_tables()

    # ── Vector Store (Qdrant) ─────────────────────────────────────────────────
    vector_store = QdrantVectorStore(
        url=env_config["qdrant_url"],
        api_key=get_env("QDRANT_API_KEY") or None,
    )
    await vector_store.create_collection(
        collection=app_config["QDRANT"]["COLLECTION_NAME"],
        vector_size=app_config["QDRANT"]["VECTOR_SIZE"],
    )
    app.state.vector_store = vector_store
    integrations_pkg._qdrant_store = vector_store  # for health check

    # ── Embeddings ────────────────────────────────────────────────────────────
    init_embeddings(
        openai_api_key=require_env("OPENAI_API_KEY"),
        embedding_model=app_config["LLM"]["EMBEDDING_MODEL"],
        fallback_model=app_config["LLM"]["EMBEDDING_FALLBACK_MODEL"],
        embedding_ttl=app_config["CACHE"]["EMBEDDING_TTL_SECONDS"],
    )

    # ── LLM (OpenAI + Flan-T5 fallback) ──────────────────────────────────────
    init_llm(
        openai_api_key=require_env("OPENAI_API_KEY"),
        l1_model=app_config["LLM"]["L1_MODEL"],
        l2_model=app_config["LLM"]["L2_MODEL"],
        fallback_model=app_config["LLM"]["FALLBACK_MODEL"],
        request_timeout=app_config["LLM"]["REQUEST_TIMEOUT_SECONDS"],
        max_retries=app_config["LLM"]["MAX_RETRIES"],
        retry_base_delay=app_config["LLM"]["RETRY_BASE_DELAY_SECONDS"],
    )

    # ── Triage graph (LangGraph — compiled once, reused per request) ─────────
    app.state.triage_graph = build_triage_graph(
        vector_store=vector_store,
        collection=app_config["QDRANT"]["COLLECTION_NAME"],
        app_config=app_config,
    )

    # ── Store configs on app.state for dependency injection ───────────────────
    app.state.app_config = app_config
    app.state.env_config = env_config

    log_info("All services initialised. Application ready.")

    yield  # Application runs here

    # ── Shutdown ──────────────────────────────────────────────────────────────
    log_info("Lifespan shutdown — cleaning up ...")


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────
app = FastAPI(
    title=app_config["APP_NAME"],
    version=app_config["APP_VERSION"],
    description=app_config["DESCRIPTION"],
    docs_url=f"{app_config['API_PREFIX']}/docs",
    redoc_url=f"{app_config['API_PREFIX']}/redoc",
    openapi_url=f"{app_config['API_PREFIX']}/openapi.json",
    lifespan=lifespan,
)

# ── CORS (allow React dev server) ─────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Exception handlers ────────────────────────────────────────────────────────
register_exception_handlers(app)

# ── Routers ───────────────────────────────────────────────────────────────────
prefix = app_config["API_PREFIX"]
app.include_router(health_router)
app.include_router(ingestion_router, prefix=prefix)
app.include_router(search_router, prefix=prefix)
app.include_router(triage_router, prefix=prefix)
app.include_router(evaluation_router, prefix=prefix)

log_info(
    "Routers registered | prefix=%s | docs=%s/docs",
    prefix,
    prefix,
)

# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=env_config.get("debug", False),
        log_level=env_config.get("log_level", "info").lower(),
    )
