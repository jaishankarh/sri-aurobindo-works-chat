"""
Reciprocal Rank Fusion (RRF) hybrid retrieval.

Blends dense vector search, sparse BM25 keyword search, and graph traversal
using the RRF formula:
    score(d, Q) = Σ 1 / (k + rank_i(d))

An alpha parameter controls the weighting between semantic (dense) and
keyword (sparse) channels:
    alpha=1.0 → pure dense semantic
    alpha=0.0 → pure BM25 keyword
    alpha=0.5 → balanced blend

Reference: Cormack, Clarke & Buettcher (2009), "Reciprocal Rank Fusion
outperforms Condorcet and individual Rank Learning Methods"
"""

import logging
import uuid
from typing import Optional

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import embed_single
from app.models.schemas import RetrievedContext, RetrievalSettings

from .graph_store import graph_retrieve
from .vector_store import search_dense, search_sparse_bm25

logger = logging.getLogger(__name__)

_RRF_K = 60  # RRF constant; standard value from original paper


def _rrf_score(rank: int, k: int = _RRF_K) -> float:
    return 1.0 / (k + rank)


def _apply_rrf(
    dense_results: list[RetrievedContext],
    sparse_results: list[RetrievedContext],
    graph_results: list[RetrievedContext],
    alpha: float,
) -> list[RetrievedContext]:
    """
    Apply Reciprocal Rank Fusion across three ranked lists.

    alpha controls dense vs sparse balance; graph results are always included
    with a fixed contribution weight.
    """
    chunk_scores: dict[uuid.UUID, float] = {}
    chunk_map: dict[uuid.UUID, RetrievedContext] = {}

    # Dense channel (weighted by alpha)
    for rank, ctx in enumerate(dense_results):
        score = alpha * _rrf_score(rank)
        chunk_scores[ctx.chunk_id] = chunk_scores.get(ctx.chunk_id, 0.0) + score
        chunk_map[ctx.chunk_id] = ctx

    # Sparse / keyword channel (weighted by 1 - alpha)
    for rank, ctx in enumerate(sparse_results):
        score = (1.0 - alpha) * _rrf_score(rank)
        chunk_scores[ctx.chunk_id] = chunk_scores.get(ctx.chunk_id, 0.0) + score
        if ctx.chunk_id not in chunk_map:
            chunk_map[ctx.chunk_id] = ctx

    # Graph channel (fixed 0.3 weight; adds complementary multi-hop context)
    for rank, ctx in enumerate(graph_results):
        score = 0.3 * _rrf_score(rank)
        chunk_scores[ctx.chunk_id] = chunk_scores.get(ctx.chunk_id, 0.0) + score
        if ctx.chunk_id not in chunk_map:
            chunk_map[ctx.chunk_id] = ctx

    # Sort by combined score descending
    sorted_ids = sorted(chunk_scores, key=lambda cid: chunk_scores[cid], reverse=True)

    results = []
    for cid in sorted_ids:
        ctx = chunk_map[cid]
        updated = ctx.model_copy(
            update={
                "relevance_score": min(1.0, chunk_scores[cid]),
                "retrieval_source": "rrf",
            }
        )
        results.append(updated)

    return results


async def hybrid_retrieve(
    session: AsyncSession,
    query: str,
    settings: RetrievalSettings,
) -> list[RetrievedContext]:
    """
    Full hybrid retrieval pipeline.

    1. Embed query (dense + sparse)
    2. Run dense ANN search
    3. Run sparse BM25 search (if alpha < 1.0)
    4. Run graph traversal (if graph_hops > 0)
    5. Fuse results with RRF
    6. Return top_k results

    Args:
        session: Async database session
        query: User's query string
        settings: RetrievalSettings controlling alpha, top_k, filters etc.

    Returns:
        Ranked list of RetrievedContext objects.
    """
    lang_filter = settings.language_filter or None
    doc_filter = settings.document_filter or None

    logger.info(
        f"Hybrid retrieval | alpha={settings.alpha} | top_k={settings.top_k} "
        f"| graph_hops={settings.graph_hops} | lang={lang_filter}"
    )

    # Embed query
    fetch_top_k = settings.top_k * 3  # fetch more, RRF trims to top_k
    embedding_result = await embed_single(query, return_sparse=True)
    query_dense = embedding_result["dense"]
    query_sparse = embedding_result.get("sparse", {})

    # Dense search (always)
    dense_results = await search_dense(
        session,
        query_embedding=query_dense,
        top_k=fetch_top_k,
        language_filter=lang_filter,
        document_filter=doc_filter,
    )

    # Sparse search (skip if alpha=1.0)
    sparse_results: list[RetrievedContext] = []
    if settings.alpha < 0.99 and query_sparse:
        sparse_results = await search_sparse_bm25(
            session,
            query_tokens=query_sparse,
            top_k=fetch_top_k,
            language_filter=lang_filter,
            document_filter=doc_filter,
        )

    # Graph traversal (skip if graph_hops=0)
    graph_results: list[RetrievedContext] = []
    if settings.graph_hops > 0:
        graph_results = await graph_retrieve(
            session,
            query=query,
            max_hops=settings.graph_hops,
            document_filter=doc_filter,
            top_k=fetch_top_k,
        )

    if not dense_results and not sparse_results and not graph_results:
        return []

    # Fuse and return top_k
    fused = _apply_rrf(dense_results, sparse_results, graph_results, settings.alpha)
    return fused[: settings.top_k]
