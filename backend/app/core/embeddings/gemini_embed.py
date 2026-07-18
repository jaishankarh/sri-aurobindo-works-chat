"""
Gemini embedding pipeline — cloud alternative to local BGE-M3.

Dense only: Gemini's embedding API has no lexical/sparse output. The sparse
BM25 retrieval channel is skipped automatically when this provider is active
(hybrid_retrieve already degrades gracefully to dense-only when the sparse
results list comes back empty), so alpha effectively behaves as 1.0.
"""

import logging
from typing import Any

import numpy as np

from app.config import settings

logger = logging.getLogger(__name__)

_EMBED_BATCH_LIMIT = 100  # Gemini batchEmbedContents limit


async def embed_texts(
    texts: list[str],
    return_sparse: bool = True,
    batch_size: int | None = None,
) -> list[dict[str, Any]]:
    """Compute dense embeddings for a list of texts via the Gemini API."""
    if not texts:
        return []

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    bs = batch_size or _EMBED_BATCH_LIMIT

    results: list[dict[str, Any]] = []
    for i in range(0, len(texts), bs):
        batch = texts[i : i + bs]
        response = await client.aio.models.embed_content(
            model=settings.EMBEDDING_MODEL,
            contents=batch,
            config=types.EmbedContentConfig(output_dimensionality=settings.EMBEDDING_DIM),
        )
        for embedding in response.embeddings:
            results.append(
                {"dense": np.array(embedding.values, dtype=np.float32), "sparse": {}}
            )

    return results


async def embed_single(text: str, return_sparse: bool = True) -> dict[str, Any]:
    """Convenience wrapper for embedding a single text."""
    results = await embed_texts([text], return_sparse=return_sparse)
    if results:
        return results[0]
    return {"dense": np.zeros(settings.EMBEDDING_DIM, dtype=np.float32), "sparse": {}}
