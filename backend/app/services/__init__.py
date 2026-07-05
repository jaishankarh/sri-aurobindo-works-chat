# Lazy imports to avoid loading heavy dependencies (PyMuPDF, torch) at module level.
# Import specific modules directly when needed.

from .streaming import (
    delete_stream,
    get_redis,
    get_stream_length,
    publish_event,
    publish_token,
    replay_then_tail,
)

__all__ = [
    "ingest_document",
    "retrieve_context",
    "generate_answer",
    "stream_answer",
    "get_redis",
    "publish_token",
    "publish_event",
    "replay_then_tail",
    "get_stream_length",
    "delete_stream",
]


def __getattr__(name: str):
    """Lazy-load heavy modules to avoid import-time dependency issues."""
    if name == "ingest_document":
        from .ingestion import ingest_document
        return ingest_document
    if name in ("generate_answer", "retrieve_context", "stream_answer"):
        from .chat import generate_answer, retrieve_context, stream_answer
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
