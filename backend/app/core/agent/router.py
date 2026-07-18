"""
Agentic RAG router step.

Given the conversation so far and the new user message, decides whether this
turn needs fresh retrieval at all, and if so, rewrites it into one or more
standalone search queries with pronouns/references resolved against history
(e.g. "its relation to X" -> "Brahman's relation to X"). Implemented via
explicit JSON-prompting rather than native tool-calling so behavior is
identical across all supported LLM providers (Ollama, OpenAI, Anthropic,
Gemini) — local-model tool-calling reliability varies too much to depend on.
"""

import logging

from app.core.llm.json_utils import parse_json_object
from app.models.schemas import TurnPlan

logger = logging.getLogger(__name__)

_ROUTER_PROMPT = """You are the routing step of a scholarly RAG assistant over the works of Sri Aurobindo and The Mother.

Given the conversation so far and the user's new message, decide:
1. Does answering this message require searching the text corpus for new passages, or can it be answered from what's already established in the conversation (e.g. "simplify that", "say more about the second point")?
2. If new search is needed, rewrite the message into 1-3 standalone search queries with all pronouns and implicit references resolved using the conversation history (e.g. "its relation to Atman" -> "Brahman's relation to Atman" if Brahman was the prior topic).

Conversation so far:
{history_transcript}

New user message:
{query}

Respond ONLY with valid JSON matching this exact structure:
{{
  "needs_retrieval": true,
  "search_queries": ["standalone query 1", "standalone query 2"],
  "reasoning": "brief reason for the decision"
}}

If the message is a pure follow-up answerable from the conversation history alone, set needs_retrieval to false and search_queries to an empty list."""

_DEFAULT_PLAN = {
    "needs_retrieval": True,
    "search_queries": [],
    "reasoning": "router failed, defaulting to direct retrieval on the raw query",
}


async def plan_turn(
    query: str,
    history_transcript: str = "",
    llm_client=None,
) -> TurnPlan:
    """
    Decide whether this conversational turn needs new retrieval, and if so,
    rewrite it into standalone search queries.

    Falls back to a single-query direct-retrieval plan (needs_retrieval=True,
    search_queries=[query]) on any LLM/parsing failure, or when there's no
    history yet (first turn in a session always needs retrieval and the raw
    query is already standalone).
    """
    if not history_transcript:
        return TurnPlan(needs_retrieval=True, search_queries=[query], reasoning="first turn")

    if llm_client is None:
        from app.core.llm.client import get_llm_client
        llm_client = get_llm_client()

    prompt = _ROUTER_PROMPT.format(history_transcript=history_transcript, query=query)

    try:
        response_text = await llm_client.generate(prompt, max_tokens=512)
        data = parse_json_object(response_text, _DEFAULT_PLAN)
    except Exception as e:
        logger.warning(f"Router LLM call failed: {e}. Defaulting to direct retrieval.")
        data = _DEFAULT_PLAN

    needs_retrieval = data.get("needs_retrieval", True)
    search_queries = data.get("search_queries") or []

    if needs_retrieval and not search_queries:
        # Model said retrieval is needed but gave no queries — fall back to the raw query.
        search_queries = [query]

    return TurnPlan(
        needs_retrieval=needs_retrieval,
        search_queries=search_queries,
        reasoning=data.get("reasoning", ""),
    )
