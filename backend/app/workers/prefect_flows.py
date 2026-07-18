"""
Prefect flows and tasks for background RAG operations.

Prefect is used instead of Celery for superior observability — each LLM call,
retrieval step, and streaming operation appears as a traceable Prefect task
with its inputs, outputs, and timing logged to the Prefect UI.

Flows:
  - ingest_document_flow: Parse, embed, and graph a single PDF
  - rag_query_flow: Agentic RAG pipeline — plan the turn, retrieve across the
    router's search queries, curate the candidate pool, stream the answer.
    Each step is its own Prefect task so it's independently traceable, and
    publishes a status event to Redis so the client can show granular
    progress instead of one long silent wait.
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


# ──────────────────────────── Agentic RAG Query Flow ─────────────────────────


@task(name="plan-turn", retries=1, retry_delay_seconds=5)
async def plan_turn_task(
    message_id: str,
    session_id: str,
    query: str,
) -> dict:
    """Fetch conversation history and let the router decide this turn's plan."""
    from app.core.agent.router import plan_turn
    from app.database import get_async_session
    from app.services.chat import format_history_transcript, get_conversation_history
    from app.services.streaming import get_redis, publish_event

    pf_logger = get_run_logger()

    redis = await get_redis()
    await publish_event(
        redis, message_id, "status",
        {"status": "planning", "detail": "Understanding your question"}
    )

    async with get_async_session() as session:
        history_messages = await get_conversation_history(session, uuid.UUID(session_id))
    history_transcript = format_history_transcript(history_messages)

    plan = await plan_turn(query, history_transcript=history_transcript)
    pf_logger.info(f"Turn plan: needs_retrieval={plan.needs_retrieval} queries={plan.search_queries}")

    return {"plan": plan.model_dump(), "history_transcript": history_transcript}


@task(name="retrieve-candidates", retries=1, retry_delay_seconds=5)
async def retrieve_candidates_task(
    message_id: str,
    settings_dict: dict,
    plan_dict: dict,
) -> list[dict]:
    """Run hybrid retrieval for every router-generated search query and merge results."""
    from app.database import get_async_session
    from app.models.schemas import RetrievalSettings, UserSettings
    from app.core.retrieval import hybrid_retrieve
    from app.services.streaming import get_redis, publish_event

    pf_logger = get_run_logger()
    plan = plan_dict["plan"]

    if not plan["needs_retrieval"]:
        pf_logger.info("Router decided no new retrieval is needed for this turn")
        return []

    redis = await get_redis()
    await publish_event(
        redis, message_id, "status",
        {"status": "retrieving", "detail": "Searching the corpus"}
    )

    user_settings = UserSettings(**settings_dict)
    retrieval_settings = RetrievalSettings(
        alpha=user_settings.alpha,
        top_k=user_settings.top_k,
        graph_hops=user_settings.graph_hops,
        language_filter=user_settings.language_filter or None,
        document_filter=user_settings.selected_document_ids or None,
    )

    candidate_map: dict[str, dict] = {}
    async with get_async_session() as session:
        for search_query in plan["search_queries"]:
            results = await hybrid_retrieve(session, search_query, retrieval_settings)
            for ctx in results:
                key = str(ctx.chunk_id)
                if key not in candidate_map:
                    candidate_map[key] = ctx.model_dump(mode="json")

    candidates = list(candidate_map.values())
    pf_logger.info(f"Retrieved {len(candidates)} merged candidates across {len(plan['search_queries'])} queries")

    await publish_event(
        redis, message_id, "status",
        {"status": "retrieving", "detail": f"Found {len(candidates)} candidate passages"}
    )

    return candidates


@task(name="select-chunks", retries=1, retry_delay_seconds=5)
async def select_chunks_task(
    message_id: str,
    query: str,
    settings_dict: dict,
    candidate_dicts: list[dict],
    plan_dict: dict,
) -> list[dict]:
    """Curate the merged candidate pool down to the chunks worth synthesizing from."""
    from app.core.agent.curator import select_chunks
    from app.models.schemas import RetrievedContext, UserSettings
    from app.services.streaming import get_redis, publish_event

    pf_logger = get_run_logger()

    if not candidate_dicts:
        return []

    redis = await get_redis()
    await publish_event(
        redis, message_id, "status",
        {"status": "selecting_sources", "detail": f"Reviewing {len(candidate_dicts)} passages"}
    )

    user_settings = UserSettings(**settings_dict)
    candidates = [RetrievedContext(**d) for d in candidate_dicts]

    selected = await select_chunks(
        query,
        candidates,
        top_k=user_settings.top_k,
        history_transcript=plan_dict["history_transcript"],
    )
    pf_logger.info(f"Curator selected {len(selected)} of {len(candidates)} candidates")

    return [ctx.model_dump(mode="json") for ctx in selected]


@task(name="stream-llm-response", retries=1, retry_delay_seconds=10)
async def stream_llm_task(
    message_id: str,
    query: str,
    context_dicts: list[dict],
    history_transcript: str,
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
    await publish_event(
        redis, message_id, "status",
        {"status": "generating", "detail": "Writing your answer"}
    )

    full_response = ""
    token_index = 0

    try:
        async for token in stream_answer(query, contexts, history_transcript=history_transcript):
            await publish_token(redis, message_id, token, token_index)
            full_response += token
            token_index += 1
    except Exception as e:
        pf_logger.error(f"Streaming error: {e}")
        await publish_event(
            redis, message_id, "error",
            {"error": str(e)}
        )
        raise

    # Extract citations from complete response
    citations = extract_citations_from_response(full_response, contexts)
    citations_json = [c.model_dump(mode="json") for c in citations]

    # Publish citations and completion signal
    await publish_event(redis, message_id, "citation", {"citations": citations_json})
    await publish_event(redis, message_id, "complete", {
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
    description="Plan the turn, retrieve across router queries, curate, stream the answer"
)
async def rag_query_flow(
    message_id: str,
    session_id: str,
    query: str,
    settings_dict: dict,
) -> dict:
    """
    Prefect flow: full agentic RAG query pipeline.

    plan_turn_task -> retrieve_candidates_task (multi-query) -> select_chunks_task
    -> stream_llm_task, each independently tracked in the Prefect UI and each
    publishing its own status event so the client sees granular progress.
    """
    plan_dict = await plan_turn_task(
        message_id=message_id,
        session_id=session_id,
        query=query,
    )

    candidate_dicts = await retrieve_candidates_task(
        message_id=message_id,
        settings_dict=settings_dict,
        plan_dict=plan_dict,
    )

    context_dicts = await select_chunks_task(
        message_id=message_id,
        query=query,
        settings_dict=settings_dict,
        candidate_dicts=candidate_dicts,
        plan_dict=plan_dict,
    )

    result = await stream_llm_task(
        message_id=message_id,
        query=query,
        context_dicts=context_dicts,
        history_transcript=plan_dict["history_transcript"],
    )

    return result
