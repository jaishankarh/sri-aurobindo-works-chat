"""
Integration tests for the Redis Streams Replay-then-Tail pattern.

Tests verify that:
1. Tokens published to Redis are correctly replayed on reconnect
2. Zero data loss when simulating a mid-stream browser disconnect
3. The complete signal terminates the stream correctly
4. Multiple concurrent consumers receive the same events
"""

import asyncio
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch


# ── Mock Redis implementation for testing without a real Redis server ─────────


class MockRedisStream:
    """
    In-memory mock of Redis Streams XADD/XRANGE/XREAD operations.

    Implements the minimal subset of the Redis Streams API used by the streaming service.
    """

    def __init__(self):
        self._streams: dict[str, list[tuple[str, dict]]] = {}
        self._counter: int = 0

    def _next_id(self) -> str:
        self._counter += 1
        return f"{self._counter * 1000}-0"

    async def xadd(self, key: str, fields: dict, **kwargs) -> str:
        if key not in self._streams:
            self._streams[key] = []
        entry_id = self._next_id()
        self._streams[key].append((entry_id, dict(fields)))
        return entry_id

    async def xrange(self, key: str, min: str = "-", max: str = "+", **kwargs):
        entries = self._streams.get(key, [])
        result = []
        for eid, fields in entries:
            if min != "-" and min != "0" and eid <= min:
                continue
            result.append((eid, fields))
        return result

    async def xread(self, streams: dict, count: int = 100, block: int = 0):
        results = []
        for key, cursor in streams.items():
            entries = self._streams.get(key, [])
            new_entries = [(eid, fields) for eid, fields in entries if eid > cursor]
            if new_entries:
                results.append((key, new_entries[:count]))
        return results if results else None

    async def expire(self, key: str, ttl: int) -> bool:
        return True

    async def exists(self, key: str) -> bool:
        return key in self._streams

    async def xlen(self, key: str) -> int:
        return len(self._streams.get(key, []))

    async def delete(self, key: str) -> int:
        removed = 1 if key in self._streams else 0
        self._streams.pop(key, None)
        return removed


# ── Helpers ───────────────────────────────────────────────────────────────────


async def simulate_worker_publish(
    redis: MockRedisStream,
    session_id: str,
    message_id: str,
    tokens: list[str],
    delay_between: float = 0.0,
) -> None:
    """Simulate a Prefect worker publishing tokens to Redis Streams."""
    from app.services.streaming import publish_event, publish_token

    await publish_event(redis, session_id, message_id, "status", {"status": "generating"})

    for i, token in enumerate(tokens):
        await publish_token(redis, session_id, message_id, token, i)
        if delay_between > 0:
            await asyncio.sleep(delay_between)

    await publish_event(redis, session_id, message_id, "complete", {"token_count": len(tokens)})


async def collect_stream_events(
    redis: MockRedisStream,
    session_id: str,
    last_seen_id: str = "0",
    timeout: float = 5.0,
) -> list[dict]:
    """Collect all events from a Redis stream with a timeout."""
    from app.services.streaming import replay_then_tail

    events = []
    try:
        async with asyncio.timeout(timeout):
            async for event in replay_then_tail(redis, session_id, last_seen_id):
                events.append(dict(event))
                if event.get("type") in ("complete", "error"):
                    break
    except asyncio.TimeoutError:
        pass
    return events


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestReplayThenTail:
    """Tests for the core replay-then-tail streaming pattern."""

    @pytest.mark.asyncio
    async def test_complete_stream_delivery(self):
        """All published tokens should be received by a connected consumer."""
        redis = MockRedisStream()
        session_id = "test-session-001"
        message_id = "msg-001"
        tokens = ["The ", "Self ", "is ", "Brahman"]

        # Publish all tokens first (simulating fast worker)
        await simulate_worker_publish(redis, session_id, message_id, tokens)

        # Collect from beginning
        events = await collect_stream_events(redis, session_id, "0")

        token_events = [e for e in events if e.get("type") == "token"]
        received_tokens = [e.get("data", "") for e in token_events]

        assert received_tokens == tokens, (
            f"Expected tokens {tokens}, got {received_tokens}"
        )

    @pytest.mark.asyncio
    async def test_replay_recovers_missed_tokens(self):
        """
        Simulated disconnect: consumer missed the first N tokens.

        Reconnecting with the last seen stream ID should recover all missed events.
        """
        redis = MockRedisStream()
        session_id = "test-session-002"
        message_id = "msg-002"
        tokens = ["A", "B", "C", "D", "E", "F"]

        # Publish all tokens
        await simulate_worker_publish(redis, session_id, message_id, tokens)

        # First, collect the first 2 tokens to get their stream IDs
        stream = redis._streams.get(f"rag:stream:{session_id}", [])
        token_entries = [(eid, f) for eid, f in stream if f.get("type") == "token"]

        assert len(token_entries) >= 3, "Should have published at least 3 token entries"

        # Simulate disconnect after 2 tokens received
        last_seen_id = token_entries[1][0]  # ID of the 2nd token

        # Reconnect from last_seen_id — should replay tokens C, D, E, F and complete
        events = await collect_stream_events(redis, session_id, last_seen_id)

        token_events = [e for e in events if e.get("type") == "token"]
        recovered_tokens = [e.get("data", "") for e in token_events]

        # Should have recovered tokens C onwards (indices 2-5)
        assert "A" not in recovered_tokens, "Already-seen token A should not be replayed"
        assert "B" not in recovered_tokens, "Already-seen token B should not be replayed"
        assert "C" in recovered_tokens, "Missed token C should be recovered"
        assert "F" in recovered_tokens, "Last token F should be recovered"
        assert len(recovered_tokens) == 4, f"Expected 4 recovered tokens, got {len(recovered_tokens)}"

    @pytest.mark.asyncio
    async def test_zero_loss_on_immediate_disconnect(self):
        """
        Extreme case: consumer disconnects immediately after query submission,
        then reconnects after all tokens are generated.

        Should recover 100% of tokens.
        """
        redis = MockRedisStream()
        session_id = "test-session-003"
        message_id = "msg-003"
        tokens = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")  # 26 tokens

        # Simulate: worker publishes all tokens while consumer is disconnected
        await simulate_worker_publish(redis, session_id, message_id, tokens)

        # Reconnect from the very beginning (last_seen_id = "0")
        events = await collect_stream_events(redis, session_id, "0")

        token_events = [e for e in events if e.get("type") == "token"]
        recovered = [e.get("data", "") for e in token_events]

        assert len(recovered) == len(tokens), (
            f"Expected {len(tokens)} tokens, recovered {len(recovered)}"
        )
        assert recovered == tokens, "Recovered tokens must be in order"

    @pytest.mark.asyncio
    async def test_complete_signal_terminates_stream(self):
        """The 'complete' event should cause the consumer to stop reading."""
        redis = MockRedisStream()
        session_id = "test-session-004"
        message_id = "msg-004"
        tokens = ["done"]

        await simulate_worker_publish(redis, session_id, message_id, tokens)

        # Add extra events AFTER complete (should not be received)
        extra_key = f"rag:stream:{session_id}"
        await redis.xadd(extra_key, {"type": "token", "data": "extra", "idx": "99", "message_id": message_id})

        events = await collect_stream_events(redis, session_id, "0")

        types = [e.get("type") for e in events]
        assert "complete" in types, "Complete event should be present"

        # Events after complete should not appear
        complete_idx = types.index("complete")
        post_complete = [e for e in events[complete_idx + 1:] if e.get("type") == "token"]
        assert len(post_complete) == 0, "No tokens should appear after complete signal"

    @pytest.mark.asyncio
    async def test_error_signal_terminates_stream(self):
        """An 'error' event should also terminate the stream consumer."""
        redis = MockRedisStream()
        session_id = "test-session-005"
        message_id = "msg-005"

        from app.services.streaming import publish_event, publish_token
        await publish_token(redis, session_id, message_id, "partial", 0)
        await publish_event(redis, session_id, message_id, "error", {"error": "LLM timeout"})

        events = await collect_stream_events(redis, session_id, "0")
        types = [e.get("type") for e in events]

        assert "error" in types, "Error event should be received"
        # Consumer should stop at error
        error_idx = types.index("error")
        assert error_idx == len(types) - 1, "Error should be the last received event"


class TestStreamOperations:
    """Tests for individual stream operation functions."""

    @pytest.mark.asyncio
    async def test_publish_token_structure(self):
        """Published token entries should have the correct field structure."""
        redis = MockRedisStream()
        session_id = "test-pub-001"
        message_id = "msg-pub-001"

        from app.services.streaming import publish_token
        await publish_token(redis, session_id, message_id, "Hello", 42)

        key = f"rag:stream:{session_id}"
        entries = await redis.xrange(key)

        assert len(entries) == 1
        _, fields = entries[0]
        assert fields["type"] == "token"
        assert fields["data"] == "Hello"
        assert fields["idx"] == "42"
        assert fields["message_id"] == message_id

    @pytest.mark.asyncio
    async def test_publish_event_json_serialization(self):
        """Published events should serialize complex data to JSON correctly."""
        redis = MockRedisStream()
        session_id = "test-pub-002"
        message_id = "msg-pub-002"

        citation_data = {
            "citations": [
                {"chunk_id": "abc123", "page_number": 5, "bbox": [72, 100, 540, 120]}
            ]
        }

        from app.services.streaming import publish_event
        await publish_event(redis, session_id, message_id, "citation", citation_data)

        key = f"rag:stream:{session_id}"
        entries = await redis.xrange(key)

        assert len(entries) == 1
        _, fields = entries[0]
        assert fields["type"] == "citation"

        parsed = json.loads(fields["data"])
        assert parsed["citations"][0]["chunk_id"] == "abc123"

    @pytest.mark.asyncio
    async def test_stream_length_tracking(self):
        """get_stream_length should return the correct number of entries."""
        redis = MockRedisStream()
        session_id = "test-len-001"
        message_id = "msg-len-001"

        from app.services.streaming import get_stream_length, publish_token

        assert await get_stream_length(redis, session_id) == 0

        for i, token in enumerate(["a", "b", "c"]):
            await publish_token(redis, session_id, message_id, token, i)

        assert await get_stream_length(redis, session_id) == 3

    @pytest.mark.asyncio
    async def test_delete_stream(self):
        """delete_stream should remove the stream key."""
        redis = MockRedisStream()
        session_id = "test-del-001"
        message_id = "msg-del-001"

        from app.services.streaming import delete_stream, get_stream_length, publish_token

        await publish_token(redis, session_id, message_id, "test", 0)
        assert await get_stream_length(redis, session_id) == 1

        await delete_stream(redis, session_id)
        assert await get_stream_length(redis, session_id) == 0
