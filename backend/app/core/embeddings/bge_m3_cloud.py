"""
Hosted BGE-M3 embedding pipeline — cloud alternative to local BGE-M3 that
uses the *same* underlying model, just run by a third-party inference
provider (DeepInfra, Together AI, Fireworks, etc.) behind an OpenAI-compatible
/v1/embeddings API. Configure EMBEDDING_BASE_URL and EMBEDDING_API_KEY to
match whichever provider you have an account with.

Because it's the same model, its dense vectors live in the same 1024-dim
space as local "bge_m3" — switching between the two providers does NOT
require re-ingestion, unlike switching to/from "gemini".

Dense only: generic OpenAI-compatible embeddings endpoints don't expose
bge-m3's sparse lexical_weights output, so the BM25 retrieval channel is
skipped automatically (same as the "gemini" provider).
"""

import logging
from typing import Any

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_EMBED_BATCH_SIZE = 96


async def embed_texts(
    texts: list[str],
    return_sparse: bool = True,
    batch_size: int | None = None,
) -> list[dict[str, Any]]:
    """Compute dense embeddings via a hosted, OpenAI-compatible bge-m3 endpoint."""
    if not texts:
        return []

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.EMBEDDING_API_KEY, base_url=settings.EMBEDDING_BASE_URL)
    bs = batch_size or _EMBED_BATCH_SIZE

    results: list[dict[str, Any]] = []
    for i in range(0, len(texts), bs):
        batch = texts[i : i + bs]
        response = await client.embeddings.create(model=settings.EMBEDDING_MODEL, input=batch)
        for item in response.data:
            results.append(
                {"dense": np.array(item.embedding, dtype=np.float32), "sparse": {}}
            )

    return results


async def embed_single(text: str, return_sparse: bool = True) -> dict[str, Any]:
    """Convenience wrapper for embedding a single text."""
    results = await embed_texts([text], return_sparse=return_sparse)
    if results:
        return results[0]
    return {"dense": np.zeros(settings.EMBEDDING_DIM, dtype=np.float32), "sparse": {}}
