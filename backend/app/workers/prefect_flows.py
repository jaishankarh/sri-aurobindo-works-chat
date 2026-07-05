"""
Prefect flows and tasks for background RAG operations.

Prefect is used instead of Celery for superior observability — each LLM call,
retrieval step, and streaming operation appears as a traceable Prefect task
with its inputs, outputs, and timing logged to the Prefect UI.

Flows:
  - ingest_document_flow: Parse, embed, and graph a single PDF
  - rag_query_flow: Retrieve, synthesize, stream tokens to Redis
"""

import asyncio
import logging
import uuid
from typing import Optional

from prefect import flow, task
from prefect.logging import get_run_logger

logger = logging.getLogger(__name__)


# ──────────────────────────── Ingestion Flow ─────────────────────────────────


@task(name="parse-and-embed", retries=2, retry_delay_seconds=10)
async def parse_and_embed_task(
    file_path: str,
    title: Optional[str],
    author: Optional[str],
    force_reingest: bool,
) -> dict:
    """Parse PDF and embed all chunks. Returns document info."""
    from app.database import get_async_session
    from app.services.ingestion import ingest_document

    pf_logger = get_run_logger()
    pf_logger.info(f"Ingesting: {file_path}")

    async with get_async_session() as session:
        doc = await ingest_document(
            session=session,
            file_path=file_path,
            title=title,
            author=author,
            force_reingest=force_reingest,
            progress_callback=lambda s: pf_logger.info(
                f"  [{s.status}] {s.progress:.0%} {s.message}"
            ),
        )
        await session.commit()
        return {"document_id": str(doc.id), "title": doc.title}


@flow(name="ingest-document", description="Parse, embed, and graph a PDF document")
async def ingest_document_flow(
    file_path: str,
    title: Optional[str] = None,
    author: Optional[str] = None,
    force_reingest: bool = False,
) -> dict:
    """Prefect flow: full document ingestion pipeline."""
    result = await parse_and_embed_task(
        file_path=file_path,
        title=title,
        author=author,
        force_reingest=force_reingest,
    )
    return result


# ──────────────────────────── RAG Query Flow ─────────────────────────────────


@task(name="retrieve-context", retries=1, retry_delay_seconds=5)
async def retrieve_context_task(
    session_id: str,
    message_id: str,
    query: str,
    settings_dict: dict,
) -> list[dict]:
    """Retrieve relevant context chunks for the query."""
    from app.database import get_async_session
    from app.models.schemas import UserSettings
    from app.services.chat import retrieve_context
    from app.services.streaming import get_redis, publish_event

    pf_logger = get_run_logger()
    pf_logger.info(f"Retrieving context for: {query[:60]}")

    user_settings = UserSettings(**settings_dict)

    redis = await get_redis()
    await publish_event(
        redis, session_id, message_id, "status",
        {"status": "retrieving", "detail": "Searching knowledge base"}
    )

    async with get_async_session() as session:
        contexts = await retrieve_context(session, query, user_settings)

    pf_logger.info(f"Retrieved {len(contexts)} chunks")
    await publish_event(
        redis, session_id, message_id, "status",
        {"status": "generating", "detail": f"Found {len(contexts)} relevant passages"}
    )

    return [ctx.model_dump(mode="json") for ctx in contexts]


@task(name="stream-llm-response", retries=1, retry_delay_seconds=10)
async def stream_llm_task(
    session_id: str,
    message_id: str,
    query: str,
    context_dicts: list[dict],
) -> dict:
    """Stream LLM tokens to Redis and persist the final message."""
    from app.core.llm.rag_prompt import extract_citations_from_response
    from app.database import get_async_session
    from app.models.database import ChatMessage
    from app.models.schemas import RetrievedContext
    from app.services.chat import stream_answer
    from app.services.streaming import get_redis, publish_event, publish_token

    pf_logger = get_run_logger()
    contexts = [RetrievedContext(**d) for d in context_dicts]

    redis = await get_redis()
    full_response = ""
    token_index = 0

    try:
        async for token in stream_answer(query, contexts):
            await publish_token(redis, session_id, message_id, token, token_index)
            full_response += token
            token_index += 1
    except Exception as e:
        pf_logger.error(f"Streaming error: {e}")
        await publish_event(
            redis, session_id, message_id, "error",
            {"error": str(e)}
        )
        raise

    # Extract citations from complete response
    citations = extract_citations_from_response(full_response, contexts)
    citations_json = [c.model_dump(mode="json") for c in citations]

    # Publish citations and completion signal
    await publish_event(redis, session_id, message_id, "citation", {"citations": citations_json})
    await publish_event(redis, session_id, message_id, "complete", {
        "message_id": message_id,
        "token_count": token_index,
    })

    # Persist final message to DB
    async with get_async_session() as db_session:
        msg = await db_session.get(ChatMessage, uuid.UUID(message_id))
        if msg:
            msg.content = full_response
            msg.citations = citations_json
            msg.is_complete = True
            await db_session.commit()

    pf_logger.info(f"Streamed {token_index} tokens, {len(citations)} citations")
    return {"token_count": token_index, "citation_count": len(citations)}


@flow(
    name="rag-query",
    description="Retrieve context, stream LLM answer, publish to Redis"
)
async def rag_query_flow(
    session_id: str,
    message_id: str,
    query: str,
    settings_dict: dict,
) -> dict:
    """
    Prefect flow: full RAG query pipeline.

    Runs retrieval and LLM streaming as separate tracked tasks,
    enabling Prefect UI visibility into each step's latency and outputs.
    """
    context_dicts = await retrieve_context_task(
        session_id=session_id,
        message_id=message_id,
        query=query,
        settings_dict=settings_dict,
    )

    result = await stream_llm_task(
        session_id=session_id,
        message_id=message_id,
        query=query,
        context_dicts=context_dicts,
    )

    return result
