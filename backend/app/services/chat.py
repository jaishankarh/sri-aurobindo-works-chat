"""
Chat service: orchestrates RAG retrieval + LLM synthesis + citation extraction.

This service is called by both the synchronous REST endpoint (for complete responses)
and the Prefect worker (for async streaming to Redis). It generates answers strictly
grounded in the corpus with bounding-box-accurate citations.
"""

import logging
import uuid
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.client import get_llm_client
from app.core.llm.rag_prompt import build_rag_prompt, extract_citations_from_response
from app.core.retrieval import hybrid_retrieve
from app.models.schemas import (
    Citation,
    RetrievalSettings,
    RetrievedContext,
    UserSettings,
)

logger = logging.getLogger(__name__)


async def retrieve_context(
    session: AsyncSession,
    query: str,
    user_settings: UserSettings,
) -> list[RetrievedContext]:
    """
    Run hybrid retrieval for a query with the given user settings.

    Returns ranked context chunks ready for synthesis.
    """
    retrieval_settings = RetrievalSettings(
        alpha=user_settings.alpha,
        top_k=user_settings.top_k,
        graph_hops=user_settings.graph_hops,
        language_filter=user_settings.language_filter or None,
        document_filter=user_settings.selected_document_ids or None,
    )

    contexts = await hybrid_retrieve(session, query, retrieval_settings)
    logger.info(f"Retrieved {len(contexts)} context chunks for query: {query[:60]}")
    return contexts


async def generate_answer(
    query: str,
    contexts: list[RetrievedContext],
    llm_model: str | None = None,
) -> tuple[str, list[Citation]]:
    """
    Generate a complete (non-streaming) RAG answer.

    Returns:
        (answer_text, citations) where citations are grounded in exact bboxes.
    """
    system_prompt, user_prompt = build_rag_prompt(query, contexts)
    llm = get_llm_client()

    response_text = await llm.generate(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=2048,
    )

    citations = extract_citations_from_response(response_text, contexts)
    return response_text, citations


async def stream_answer(
    query: str,
    contexts: list[RetrievedContext],
) -> AsyncIterator[str]:
    """
    Stream LLM answer tokens one by one.

    The caller is responsible for publishing tokens to Redis via the streaming service.
    """
    system_prompt, user_prompt = build_rag_prompt(query, contexts)
    llm = get_llm_client()

    async for token in llm.stream(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=2048,
    ):
        yield token
