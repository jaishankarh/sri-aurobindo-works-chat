"""User and global settings management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db_session
from app.models.database import ChatSession
from app.models.schemas import UserSettings

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/sessions/{session_id}", response_model=UserSettings)
async def get_session_settings(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> UserSettings:
    """Get settings for an existing chat session."""
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.settings:
        return UserSettings(**session.settings)
    return UserSettings()


@router.put("/sessions/{session_id}", response_model=UserSettings)
async def update_session_settings(
    session_id: uuid.UUID,
    settings: UserSettings,
    db: AsyncSession = Depends(get_db_session),
) -> UserSettings:
    """Update settings for an existing chat session."""
    session = await db.get(ChatSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    session.settings = settings.model_dump()
    return settings


@router.post("/sessions", response_model=dict)
async def create_session(
    settings: UserSettings,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Create a new chat session with the given settings."""
    chat_session = ChatSession(settings=settings.model_dump())
    db.add(chat_session)
    await db.flush()
    return {"session_id": str(chat_session.id)}
