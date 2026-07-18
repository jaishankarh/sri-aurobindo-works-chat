"""
Agentic RAG curation step.

Given a merged candidate pool from multi-query hybrid retrieval, decides
which chunks are actually useful for answering the current question in the
context of the conversation so far — able to discard high-scoring-but-off-topic
chunks and prefer, say, prose commentary over a raw un-annotated verse when
the user wants an explanation. This is the "agentic framework decides which
chunks to pick" requirement, not just top-K similarity. Bounded to a single
pass (not an iterative agent loop) to keep latency/cost predictable.
"""

import logging

from app.core.llm.json_utils import parse_json_object
from app.models.schemas import RetrievedContext

logger = logging.getLogger(__name__)

_CURATOR_PROMPT = """You are the source-selection step of a scholarly RAG assistant over the works of Sri Aurobindo and The Mother.

Given the conversation so far, the user's question, and a pool of candidate passages retrieved from the corpus, select which passages are genuinely useful for answering this question. Discard passages that are only superficially similar but don't actually help. Prefer passages whose form fits what's being asked (e.g. prose commentary over a raw, un-annotated verse when the user wants an explanation).

Conversation so far:
{history_transcript}

User's question:
{query}

Candidate passages:
{candidates_block}

Respond ONLY with valid JSON matching this exact structure:
{{
  "selected_indices": [1, 3, 4]
}}

Select at most {top_k} passages, ordered by usefulness (most useful first). Use the [N] index shown before each candidate."""

_CANDIDATE_TEMPLATE = """[{index}] (source: {retrieval_source}, type: {chunk_type}, language: {language})
Document: {title}
{text}
"""


async def select_chunks(
    query: str,
    candidates: list[RetrievedContext],
    top_k: int,
    history_transcript: str = "",
    llm_client=None,
) -> list[RetrievedContext]:
    """
    Curate the merged candidate pool down to the top_k chunks actually worth
    sending to synthesis, using conversation context to judge relevance.

    Falls back to the candidates' existing relevance-score ordering (i.e. the
    pre-curation ranking from hybrid retrieval) on any LLM/parsing failure,
    or trivially when the pool already fits within top_k.
    """
    if not candidates:
        return []

    if len(candidates) <= top_k:
        return candidates

    fallback = sorted(candidates, key=lambda c: c.relevance_score, reverse=True)[:top_k]

    if llm_client is None:
        from app.core.llm.client import get_llm_client
        llm_client = get_llm_client()

    candidates_block = "\n".join(
        _CANDIDATE_TEMPLATE.format(
            index=i + 1,
            retrieval_source=c.retrieval_source,
            chunk_type=c.chunk_type,
            language=c.language_tag,
            title=c.document_title,
            text=c.text[:800],
        )
        for i, c in enumerate(candidates)
    )

    prompt = _CURATOR_PROMPT.format(
        history_transcript=history_transcript or "(none — first turn)",
        query=query,
        candidates_block=candidates_block,
        top_k=top_k,
    )

    try:
        response_text = await llm_client.generate(prompt, max_tokens=512)
        data = parse_json_object(response_text, {"selected_indices": []})
    except Exception as e:
        logger.warning(f"Curator LLM call failed: {e}. Falling back to score ranking.")
        return fallback

    indices = data.get("selected_indices") or []
    selected = []
    seen = set()
    for idx in indices:
        pos = idx - 1
        if isinstance(idx, int) and 0 <= pos < len(candidates) and pos not in seen:
            seen.add(pos)
            selected.append(candidates[pos])
        if len(selected) >= top_k:
            break

    return selected if selected else fallback
