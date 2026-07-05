"""
BGE-M3 embedding pipeline for dense and sparse (lexical) embeddings.

BAAI/bge-m3 is a single model that outputs:
  - Dense embeddings (1024-dim) for semantic similarity
  - Sparse (lexical) embeddings (BM25-style token weights) for keyword matching
  - ColBERT multi-vector representations (optional, for fine-grained matching)

This implementation uses FlagEmbedding for maximum compatibility with bge-m3.
"""

import asyncio
import logging
from typing import Any

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_model_instance = None
_model_lock = asyncio.Lock()


async def get_model():
    """Singleton accessor for the BGE-M3 model (loaded once per process)."""
    global _model_instance
    if _model_instance is not None:
        return _model_instance

    async with _model_lock:
        if _model_instance is not None:
            return _model_instance

        logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
        # Load in executor to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        _model_instance = await loop.run_in_executor(None, _load_model)
        logger.info("Embedding model loaded successfully")
        return _model_instance


def _load_model():
    """Load BGE-M3 using FlagEmbedding (preferred) or sentence-transformers fallback."""
    try:
        from FlagEmbedding import BGEM3FlagModel

        model = BGEM3FlagModel(
            settings.EMBEDDING_MODEL,
            use_fp16=(settings.EMBEDDING_DEVICE != "cpu"),
            device=settings.EMBEDDING_DEVICE,
        )
        return {"type": "flag", "model": model}
    except ImportError:
        logger.warning("FlagEmbedding not available, falling back to sentence-transformers")
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(
            settings.EMBEDDING_MODEL,
            device=settings.EMBEDDING_DEVICE,
        )
        return {"type": "st", "model": model}


async def embed_texts(
    texts: list[str],
    return_sparse: bool = True,
    batch_size: int | None = None,
) -> list[dict[str, Any]]:
    """
    Compute dense and sparse embeddings for a list of texts.

    Args:
        texts: List of text strings to embed.
        return_sparse: Whether to also compute sparse lexical weights.
        batch_size: Override the configured batch size.

    Returns:
        List of dicts with keys:
          - "dense": np.ndarray of shape (1024,)
          - "sparse": dict of {token_id: weight} (if return_sparse=True)
    """
    if not texts:
        return []

    bs = batch_size or settings.EMBEDDING_BATCH_SIZE
    model_wrapper = await get_model()
    loop = asyncio.get_event_loop()

    results = []
    for i in range(0, len(texts), bs):
        batch = texts[i : i + bs]
        batch_results = await loop.run_in_executor(
            None, _embed_batch, model_wrapper, batch, return_sparse
        )
        results.extend(batch_results)

    return results


def _embed_batch(
    model_wrapper: dict, texts: list[str], return_sparse: bool
) -> list[dict]:
    """Synchronous embedding computation for a single batch."""
    if model_wrapper["type"] == "flag":
        return _embed_flag(model_wrapper["model"], texts, return_sparse)
    else:
        return _embed_st(model_wrapper["model"], texts)


def _embed_flag(model, texts: list[str], return_sparse: bool) -> list[dict]:
    """Embed using FlagEmbedding BGEM3FlagModel."""
    output = model.encode(
        texts,
        return_dense=True,
        return_sparse=return_sparse,
        return_colbert_vecs=False,
        max_length=settings.EMBEDDING_MAX_LENGTH,
    )

    dense_vecs = output["dense_vecs"]
    sparse_vecs = output.get("lexical_weights", [{}] * len(texts))

    results = []
    for i in range(len(texts)):
        entry: dict[str, Any] = {"dense": dense_vecs[i].astype(np.float32)}
        if return_sparse and sparse_vecs:
            entry["sparse"] = dict(sparse_vecs[i]) if sparse_vecs[i] else {}
        else:
            entry["sparse"] = {}
        results.append(entry)
    return results


def _embed_st(model, texts: list[str]) -> list[dict]:
    """Embed using sentence-transformers (dense only)."""
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return [{"dense": emb.astype(np.float32), "sparse": {}} for emb in embeddings]


async def embed_single(text: str, return_sparse: bool = True) -> dict[str, Any]:
    """Convenience wrapper for embedding a single text."""
    results = await embed_texts([text], return_sparse=return_sparse)
    return results[0] if results else {"dense": np.zeros(1024, dtype=np.float32), "sparse": {}}


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two dense vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def sparse_dot_product(sparse_a: dict, sparse_b: dict) -> float:
    """Compute dot product between two sparse (token_id → weight) vectors."""
    common_keys = set(sparse_a.keys()) & set(sparse_b.keys())
    return sum(sparse_a[k] * sparse_b[k] for k in common_keys)
