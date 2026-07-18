"""
Chat service: orchestrates agentic RAG retrieval + LLM synthesis + citation extraction.

This service is called by both the synchronous REST endpoint (for complete responses)
and the Prefect worker (for async streaming to Redis). It generates answers strictly
grounded in the corpus (and, for follow-up turns, the conversation history) with
bounding-box-accurate citations.

The agentic pipeline is Router -> multi-query Retriever -> Curator -> Generator:
see app/core/agent/router.py and app/core/agent/curator.py. Every retrieval call
in the fan-out reuses the same RetrievalSettings built once from user_settings, so
the user's document-selection filter is honoured identically across all queries.
"""

import logging
import uuid
from typing import AsyncIterator, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent.curator import select_chunks
from app.core.agent.router import plan_turn
from app.core.llm.client import get_llm_client
from app.core.llm.rag_prompt import build_rag_prompt, extract_citations_from_response
from app.core.retrieval import hybrid_retrieve
from app.models.database import ChatMessage
from app.models.schemas import (
    Citation,
    RetrievalSettings,
    RetrievedContext,
    TurnPlan,
    UserSettings,
)

logger = logging.getLogger(__name__)

_HISTORY_LIMIT = 8


async def get_conversation_history(
    session: AsyncSession,
    session_id: uuid.UUID,
    limit: int = _HISTORY_LIMIT,
) -> list[ChatMessage]:
    """Fetch the last `limit` messages for a session, oldest first."""
    result = await session.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
    )
    messages = list(result.scalars().all())
    messages.reverse()
    return messages


def format_history_transcript(messages: list[ChatMessage]) -> str:
    """
    Render prior turns into a compact transcript for the router/curator/synthesis
    prompts, including prior citation titles/pages so the model can refer back to
    them (e.g. "as I mentioned from Isha Upanishad p.35...").
    """
    if not messages:
        return ""

    lines = []
    for msg in messages:
        speaker = "User" if msg.role == "user" else "Assistant"
        lines.append(f"{speaker}: {msg.content}")
        if msg.role == "assistant" and msg.citations:
            sources = ", ".join(
                f"{c.get('document_title', '?')} p.{c.get('page_number', '?')}"
                for c in msg.citations[:5]
            )
            if sources:
                lines.append(f"  (sources cited: {sources})")

    return "\n".join(lines)


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


async def agentic_retrieve(
    session: AsyncSession,
    query: str,
    user_settings: UserSettings,
    history_transcript: str = "",
) -> tuple[TurnPlan, list[RetrievedContext]]:
    """
    Full agentic retrieval pipeline for one conversational turn:
    1. Router decides whether this turn needs new retrieval, and rewrites the
       query into 1-3 standalone search queries if so.
    2. Every search query is retrieved with hybrid_retrieve() using the exact
       same RetrievalSettings derived from user_settings — the document filter
       and every other setting apply identically to each query in the fan-out.
    3. Candidates are merged/deduped by chunk_id into one pool.
    4. Curator selects the final top_k chunks from the pool given the question
       and conversation context.

    Returns (plan, selected_contexts). selected_contexts is empty when the
    router decided no new retrieval was needed for this turn.
    """
    plan = await plan_turn(query, history_transcript=history_transcript)

    if not plan.needs_retrieval:
        return plan, []

    retrieval_settings = RetrievalSettings(
        alpha=user_settings.alpha,
        top_k=user_settings.top_k,
        graph_hops=user_settings.graph_hops,
        language_filter=user_settings.language_filter or None,
        document_filter=user_settings.selected_document_ids or None,
    )

    candidate_map: dict[uuid.UUID, RetrievedContext] = {}
    for search_query in plan.search_queries:
        results = await hybrid_retrieve(session, search_query, retrieval_settings)
        for ctx in results:
            if ctx.chunk_id not in candidate_map:
                candidate_map[ctx.chunk_id] = ctx

    candidates = list(candidate_map.values())
    logger.info(
        f"Agentic retrieval: {len(plan.search_queries)} queries -> "
        f"{len(candidates)} merged candidates for turn: {query[:60]}"
    )

    selected = await select_chunks(
        query,
        candidates,
        top_k=user_settings.top_k,
        history_transcript=history_transcript,
    )
    return plan, selected


async def generate_answer(
    query: str,
    contexts: list[RetrievedContext],
    llm_model: str | None = None,
    history_transcript: str = "",
) -> tuple[str, list[Citation]]:
    """
    Generate a complete (non-streaming) RAG answer.

    Returns:
        (answer_text, citations) where citations are grounded in exact bboxes.
    """
    system_prompt, user_prompt = build_rag_prompt(query, contexts, history_transcript=history_transcript)
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
    history_transcript: str = "",
) -> AsyncIterator[str]:
    """
    Stream LLM answer tokens one by one.

    The caller is responsible for publishing tokens to Redis via the streaming service.
    """
    system_prompt, user_prompt = build_rag_prompt(query, contexts, history_transcript=history_transcript)
    llm = get_llm_client()

    async for token in llm.stream(
        prompt=user_prompt,
        system_prompt=system_prompt,
        max_tokens=2048,
    ):
        yield token
