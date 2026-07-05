"""
Redis Streams-based token streaming service.

Implements the "Replay-then-Tail" pattern for resilient WebSocket delivery:

1. The Prefect worker appends LLM tokens to a Redis Stream (XADD).
2. When a WebSocket client connects (or reconnects), it:
   a. XRANGE reads all previously generated tokens (REPLAY)
   b. Subscribes to new entries in real-time (TAIL)

This guarantees zero token loss even if the browser is closed during generation.
The stream is keyed by session_id and expires after REDIS_SESSION_TTL seconds.
"""

import asyncio
import json
import logging
from typing import AsyncIterator, Optional

import redis.asyncio as aioredis

from app.config import settings

logger = logging.getLogger(__name__)

_STREAM_FIELD_TYPE = "type"
_STREAM_FIELD_DATA = "data"
_STREAM_FIELD_INDEX = "idx"
_STREAM_READ_BLOCK_MS = 1000  # block for 1s waiting for new entries
_STREAM_READ_COUNT = 100  # entries per read batch


def _stream_key(session_id: str) -> str:
    return settings.REDIS_STREAM_KEY.format(session_id=session_id)


async def get_redis() -> aioredis.Redis:
    """Get an async Redis client."""
    return aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )


async def publish_token(
    redis: aioredis.Redis,
    session_id: str,
    message_id: str,
    token: str,
    token_index: int,
) -> None:
    """
    Append a single token to the Redis Stream.

    Each stream entry is identified by its auto-generated stream ID (e.g., "1234567890-0"),
    which provides ordering guarantees without a separate sequence counter.
    """
    key = _stream_key(session_id)
    await redis.xadd(
        key,
        {
            _STREAM_FIELD_TYPE: "token",
            _STREAM_FIELD_DATA: token,
            _STREAM_FIELD_INDEX: str(token_index),
            "message_id": message_id,
        },
    )
    await redis.expire(key, settings.REDIS_SESSION_TTL)


async def publish_event(
    redis: aioredis.Redis,
    session_id: str,
    message_id: str,
    event_type: str,
    data: dict,
) -> None:
    """Publish a non-token event (citation, status, complete, error) to the stream."""
    key = _stream_key(session_id)
    await redis.xadd(
        key,
        {
            _STREAM_FIELD_TYPE: event_type,
            _STREAM_FIELD_DATA: json.dumps(data),
            _STREAM_FIELD_INDEX: "-1",
            "message_id": message_id,
        },
    )
    await redis.expire(key, settings.REDIS_SESSION_TTL)


async def replay_then_tail(
    redis: aioredis.Redis,
    session_id: str,
    last_seen_id: str = "0",
) -> AsyncIterator[dict]:
    """
    Replay historical stream entries then continuously tail new ones.

    Yields stream entry dicts with keys: type, data, idx, message_id.

    Algorithm:
    1. XRANGE from last_seen_id to get all replay entries (historical)
    2. Set cursor to the last replay entry's ID
    3. XREAD with BLOCK to wait for and yield new entries (tail)
    4. Terminate when a "complete" or "error" event is seen

    Args:
        redis: Async Redis client
        session_id: The chat session ID
        last_seen_id: Redis stream ID to replay from ("0" = from beginning)
    """
    key = _stream_key(session_id)
    cursor = last_seen_id

    # Phase 1: REPLAY — read all existing entries from cursor
    replay_entries = await redis.xrange(key, min=cursor, max="+")
    for entry_id, fields in replay_entries:
        yield {**fields, "_stream_id": entry_id}
        cursor = entry_id

        # Stop replaying if we hit a terminal event
        if fields.get(_STREAM_FIELD_TYPE) in ("complete", "error"):
            return

    # Phase 2: TAIL — block-read for new entries
    while True:
        results = await redis.xread(
            {key: cursor},
            count=_STREAM_READ_COUNT,
            block=_STREAM_READ_BLOCK_MS,
        )

        if not results:
            # No new entries in this block window — check if stream key exists
            exists = await redis.exists(key)
            if not exists:
                break
            continue

        for _key, entries in results:
            for entry_id, fields in entries:
                yield {**fields, "_stream_id": entry_id}
                cursor = entry_id

                if fields.get(_STREAM_FIELD_TYPE) in ("complete", "error"):
                    return


async def get_stream_length(redis: aioredis.Redis, session_id: str) -> int:
    """Return the number of entries currently in the session stream."""
    return await redis.xlen(_stream_key(session_id))


async def delete_stream(redis: aioredis.Redis, session_id: str) -> None:
    """Delete the Redis stream for a session (cleanup)."""
    await redis.delete(_stream_key(session_id))
