"""
Chat API: REST endpoint and WebSocket endpoint for RAG Q&A.

WebSocket protocol (Replay-then-Tail):
  Client → { "type": "query", "query": "...", "session_id": "...", "settings": {...} }
  Server → { "type": "status", "data": {...} }
  Server → { "type": "token", "data": "token_text", "idx": 0 }
  Server → { "type": "citation", "data": { "citations": [...] } }
  Server → { "type": "complete", "data": {...} }
  Server → { "type": "error", "data": {"error": "..."} }

On reconnect, the client sends its last_seen_id (Redis stream ID) and the
server replays all missed events before tailing new ones.
"""

import json
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.database import ChatMessage, ChatSession
from app.models.schemas import (
    ChatMessageResponse,
    ChatRequest,
    IngestionStatus,
    UserSettings,
)
from app.services.streaming import get_redis, replay_then_tail

router = APIRouter(prefix="/chat", tags=["Chat"])
logger = logging.getLogger(__name__)


@router.post("/query", response_model=ChatMessageResponse)
async def chat_query(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ChatMessageResponse:
    """
    Non-streaming chat endpoint. Useful for programmatic access and testing.

    Runs retrieval + generation synchronously and returns the complete answer.
    """
    from app.services.chat import generate_answer, retrieve_context

    # Resolve or create session
    session_id = request.session_id
    if session_id is None:
        chat_session = ChatSession(settings=request.settings.model_dump())
        db.add(chat_session)
        await db.flush()
        session_id = chat_session.id
    else:
        chat_session = await db.get(ChatSession, session_id)
        if not chat_session:
            raise HTTPException(status_code=404, detail="Session not found")

    # Store user message
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=request.query,
        is_complete=True,
    )
    db.add(user_msg)

    # Retrieve and generate
    contexts = await retrieve_context(db, request.query, request.settings)
    answer_text, citations = await generate_answer(request.query, contexts)

    citations_json = [c.model_dump(mode="json") for c in citations]

    # Store assistant message
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=answer_text,
        citations=citations_json,
        is_complete=True,
    )
    db.add(assistant_msg)
    await db.flush()

    return ChatMessageResponse(
        id=assistant_msg.id,
        session_id=session_id,
        role="assistant",
        content=answer_text,
        citations=citations,
        is_complete=True,
    )


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageResponse])
async def get_session_messages(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> list[ChatMessageResponse]:
    """Retrieve all messages for a chat session."""
    from sqlalchemy import select

    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
    )
    messages = result.scalars().all()
    return [ChatMessageResponse.model_validate(m) for m in messages]


@router.websocket("/ws/{session_id}")
async def websocket_chat(
    websocket: WebSocket,
    session_id: str,
) -> None:
    """
    WebSocket endpoint for streaming chat with Replay-then-Tail recovery.

    Protocol:
    1. Client sends a query message or a reconnect message with last_seen_id.
    2. Server runs rag_query_flow as a background Prefect flow.
    3. Server streams all tokens from Redis (replaying missed ones on reconnect).
    """
    await websocket.accept()
    logger.info(f"WebSocket connected: session={session_id}")

    try:
        raw = await websocket.receive_text()
        msg = json.loads(raw)
    except Exception as e:
        await websocket.send_json({"type": "error", "data": {"error": f"Invalid message: {e}"}})
        await websocket.close()
        return

    msg_type = msg.get("type", "query")
    query = msg.get("query", "")
    settings_dict = msg.get("settings", {})
    last_seen_id = msg.get("last_seen_id", "0")

    redis = await get_redis()

    if msg_type == "reconnect":
        # Pure reconnect: just replay + tail the existing stream
        logger.info(f"Reconnect from last_seen_id={last_seen_id}")
        await _stream_from_redis(websocket, redis, session_id, last_seen_id)
        return

    if not query:
        await websocket.send_json({"type": "error", "data": {"error": "query is required"}})
        await websocket.close()
        return

    # Create a new message record
    message_id = str(uuid.uuid4())

    # Persist placeholder in DB
    async with __import__("app.database", fromlist=["get_async_session"]).get_async_session() as db:
        # Resolve or create session
        from app.database import AsyncSessionLocal
        async with AsyncSessionLocal() as db_session:
            chat_session = await db_session.get(ChatSession, uuid.UUID(session_id))
            if chat_session is None:
                chat_session = ChatSession(
                    id=uuid.UUID(session_id),
                    settings=settings_dict,
                )
                db_session.add(chat_session)
                await db_session.flush()

            user_msg = ChatMessage(
                session_id=uuid.UUID(session_id),
                role="user",
                content=query,
                is_complete=True,
            )
            db_session.add(user_msg)

            assistant_msg = ChatMessage(
                id=uuid.UUID(message_id),
                session_id=uuid.UUID(session_id),
                role="assistant",
                content="",
                is_complete=False,
            )
            db_session.add(assistant_msg)
            await db_session.commit()

    # Publish status: thinking
    from app.services.streaming import publish_event
    await publish_event(redis, session_id, message_id, "status", {"status": "thinking"})

    # Launch Prefect flow in background
    import asyncio
    from app.workers.prefect_flows import rag_query_flow

    asyncio.create_task(
        rag_query_flow(
            session_id=session_id,
            message_id=message_id,
            query=query,
            settings_dict=settings_dict,
        )
    )

    # Stream from Redis to WebSocket
    await _stream_from_redis(websocket, redis, session_id, "0")


async def _stream_from_redis(
    websocket: WebSocket,
    redis,
    session_id: str,
    last_seen_id: str,
) -> None:
    """Relay all Redis stream events to the WebSocket client."""
    try:
        async for entry in replay_then_tail(redis, session_id, last_seen_id=last_seen_id):
            event_type = entry.get("type", "token")
            raw_data = entry.get("data", "")

            if event_type == "token":
                payload = {
                    "type": "token",
                    "data": raw_data,
                    "idx": int(entry.get("idx", 0)),
                    "session_id": session_id,
                }
            else:
                try:
                    data = json.loads(raw_data) if raw_data else {}
                except (json.JSONDecodeError, TypeError):
                    data = {"raw": raw_data}
                payload = {
                    "type": event_type,
                    "data": data,
                    "session_id": session_id,
                }

            await websocket.send_json(payload)

            if event_type in ("complete", "error"):
                break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session={session_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "data": {"error": str(e)}})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
