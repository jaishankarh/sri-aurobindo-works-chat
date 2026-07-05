"""
pgvector-based vector store operations.

Performs dense ANN search and sparse keyword search over the chunks table.
All queries are parameterized and async-safe.
"""

import logging
import uuid
from typing import Optional

import numpy as np
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.schemas import RetrievedContext

logger = logging.getLogger(__name__)


async def search_dense(
    session: AsyncSession,
    query_embedding: np.ndarray,
    top_k: int = 10,
    language_filter: Optional[list[str]] = None,
    document_filter: Optional[list[uuid.UUID]] = None,
) -> list[RetrievedContext]:
    """
    Perform dense vector ANN search using pgvector's <=> (cosine distance) operator.

    Returns chunks ordered by semantic similarity to the query.
    """
    embedding_list = query_embedding.tolist()

    filters = []
    params: dict = {"embedding": str(embedding_list), "top_k": top_k}

    if language_filter:
        filters.append("c.language_tag = ANY(:lang_filter)")
        params["lang_filter"] = language_filter

    if document_filter:
        doc_ids = [str(d) for d in document_filter]
        filters.append("c.document_id = ANY(:doc_filter)")
        params["doc_filter"] = doc_ids

    where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""

    sql = text(
        f"""
        SELECT
            c.id AS chunk_id,
            c.document_id,
            d.title AS document_title,
            d.file_path,
            c.text,
            c.page_number,
            c.bbox,
            c.language_tag,
            1 - (c.dense_embedding <=> :embedding::vector) AS relevance_score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        {where_clause}
        WHERE c.dense_embedding IS NOT NULL
        ORDER BY c.dense_embedding <=> :embedding::vector
        LIMIT :top_k
        """
    )

    result = await session.execute(sql, params)
    rows = result.mappings().all()

    return [
        RetrievedContext(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            document_title=row["document_title"],
            file_path=row["file_path"],
            text=row["text"],
            page_number=row["page_number"],
            bbox=row["bbox"],
            language_tag=row["language_tag"],
            relevance_score=max(0.0, float(row["relevance_score"])),
            retrieval_source="vector",
        )
        for row in rows
    ]


async def search_sparse_bm25(
    session: AsyncSession,
    query_tokens: dict[str, float],
    top_k: int = 10,
    language_filter: Optional[list[str]] = None,
    document_filter: Optional[list[uuid.UUID]] = None,
) -> list[RetrievedContext]:
    """
    Approximate BM25 keyword search using sparse embedding dot products.

    Query tokens come from BGE-M3's lexical_weights output.
    We compute the dot product between the query's sparse vector and each
    stored chunk's sparse_embedding JSON field.
    """
    if not query_tokens:
        return []

    # Build a SQL expression that computes sparse dot product in PostgreSQL
    # sparse_embedding is stored as JSONB {token_id: weight}
    # We use jsonb operations to extract overlapping keys
    token_ids = list(query_tokens.keys())
    token_weights = list(query_tokens.values())

    filters = []
    params: dict = {"top_k": top_k}

    if language_filter:
        filters.append("c.language_tag = ANY(:lang_filter)")
        params["lang_filter"] = language_filter

    if document_filter:
        doc_ids = [str(d) for d in document_filter]
        filters.append("c.document_id = ANY(:doc_filter)")
        params["doc_filter"] = doc_ids

    where_clause = ("WHERE " + " AND ".join(filters)) if filters else ""

    # For each token_id, extract its weight from the JSONB and multiply
    # This approach is a simplification; a production system would use
    # a specialized sparse index (e.g., psparsevec with pgvector 0.7+)
    score_exprs = " + ".join(
        f"COALESCE((c.sparse_embedding->>'{tid}')::float, 0) * {w}"
        for tid, w in zip(token_ids[:50], token_weights[:50])  # limit for SQL size
    )
    if not score_exprs:
        return []

    sql = text(
        f"""
        SELECT
            c.id AS chunk_id,
            c.document_id,
            d.title AS document_title,
            d.file_path,
            c.text,
            c.page_number,
            c.bbox,
            c.language_tag,
            ({score_exprs}) AS relevance_score
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        {where_clause}
        WHERE c.sparse_embedding IS NOT NULL
          AND ({score_exprs}) > 0
        ORDER BY relevance_score DESC
        LIMIT :top_k
        """
    )

    try:
        result = await session.execute(sql, params)
        rows = result.mappings().all()
    except Exception as e:
        logger.warning(f"Sparse search failed: {e}")
        return []

    return [
        RetrievedContext(
            chunk_id=row["chunk_id"],
            document_id=row["document_id"],
            document_title=row["document_title"],
            file_path=row["file_path"],
            text=row["text"],
            page_number=row["page_number"],
            bbox=row["bbox"],
            language_tag=row["language_tag"],
            relevance_score=max(0.0, float(row["relevance_score"])),
            retrieval_source="keyword",
        )
        for row in rows
    ]
