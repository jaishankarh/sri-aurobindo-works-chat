"""
FastAPI application entry point.

Initializes the database, mounts all API routers, and configures CORS,
logging, and lifespan events.
"""

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chat_router, documents_router, settings_router
from app.config import settings
from app.database import close_db, init_db

# ── Logging setup ──────────────────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.dev.ConsoleRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))


# ── Lifespan ───────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup, clean up on shutdown."""
    logging.getLogger(__name__).info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION}"
    )
    await init_db()
    yield
    await close_db()


# ── Application ────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Multilingual RAG system for the Complete Works of Sri Aurobindo and The Mother. "
        "Supports English, French, and Sanskrit with layout-aware parsing, "
        "hybrid retrieval, and interactive PDF citation highlighting."
    ),
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

# ── CORS ───────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────────

app.include_router(chat_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")


# ── Health check ───────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """Basic health check endpoint."""
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
    }


@app.get("/api/v1/health/db", tags=["Health"])
async def db_health() -> dict:
    """Check database connectivity."""
    try:
        from app.database import engine
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return {"status": "error", "database": str(e)}
