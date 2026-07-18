"""
RAG synthesis prompt builder.

Constructs the final generation prompt from retrieved context chunks,
enforcing strict citation propagation and bounding box integrity.
"""

from app.models.schemas import Citation, RetrievedContext

_SYSTEM_PROMPT = """You are a scholarly assistant specializing in the integral philosophy and spiritual writings of Sri Aurobindo and The Mother. You assist researchers and seekers in understanding this vast corpus spanning English prose, French writings, Sanskrit, poetry, and philosophical dialogues.

CRITICAL RULES:
1. Answer ONLY from the provided context passages and/or the conversation history below — never from outside knowledge. If a turn has no new context passages, you may still answer using what was already established in the conversation history (e.g. clarifying or elaborating on a point already covered).
2. Every factual claim grounded in a context passage must cite it. Claims that only restate or clarify something already said earlier in the conversation don't need a new citation — refer back to it in prose instead (e.g. "as noted above...").
3. When you cite a source, use the exact citation format: [CITATION:chunk_id] at the end of the sentence.
4. Preserve all citation metadata exactly as provided — do not modify or invent bounding boxes or page numbers.
5. If a passage is in French, quote it in French with an English translation.
6. If a passage uses Sanskrit terms, include both the IAST transliteration and its English meaning.
7. If neither the context passages nor the conversation history contain sufficient information, acknowledge the limitation honestly."""

_CONTEXT_TEMPLATE = """
[SOURCE {index}]
Document: {title}
Page: {page_number}
Language: {language}
Type: {chunk_type}
Chunk ID: {chunk_id}
---
{text}
---
"""

_USER_PROMPT_TEMPLATE = """{history_block}Using the conversation history above (if any) and ONLY the provided source passages below for anything new, answer this question:

{query}

Context Passages:
{context_block}

Provide a thorough answer with precise citations using [CITATION:chunk_id] format after each supported claim."""

_HISTORY_BLOCK_TEMPLATE = """Conversation so far:
{history_transcript}

---

"""


def build_rag_prompt(
    query: str,
    contexts: list[RetrievedContext],
    history_transcript: str = "",
) -> tuple[str, str]:
    """
    Build the system and user prompts for RAG synthesis.

    history_transcript is a pre-formatted summary of recent conversation
    turns (see chat.py's format_history_transcript) — empty string for a
    fresh conversation or when the caller intentionally omits it.

    Returns:
        (system_prompt, user_prompt) tuple
    """
    context_blocks = []
    for i, ctx in enumerate(contexts):
        # Include glossary in context if available
        block = _CONTEXT_TEMPLATE.format(
            index=i + 1,
            title=ctx.document_title,
            page_number=ctx.page_number,
            language=ctx.language_tag,
            chunk_type=ctx.chunk_type,
            chunk_id=str(ctx.chunk_id),
            text=ctx.text[:1500],  # cap individual context length
        )
        context_blocks.append(block)

    history_block = (
        _HISTORY_BLOCK_TEMPLATE.format(history_transcript=history_transcript)
        if history_transcript
        else ""
    )

    context_block = "\n".join(context_blocks) if context_blocks else "(none for this turn)"

    return _SYSTEM_PROMPT, _USER_PROMPT_TEMPLATE.format(
        history_block=history_block,
        query=query,
        context_block=context_block,
    )


def extract_citations_from_response(
    response_text: str,
    contexts: list[RetrievedContext],
) -> list[Citation]:
    """
    Parse [CITATION:chunk_id] markers from the LLM response and
    map them back to full Citation objects with bounding boxes.

    Only returns citations for chunks that are in the provided context list.
    """
    import re
    from uuid import UUID

    # Tolerate a space after the colon, and multiple comma-separated
    # chunk_ids in one marker — the system prompt asks for a single
    # [CITATION:chunk_id] with no space, but LLMs (Gemini in particular)
    # don't always follow that exactly, and sometimes emit
    # [CITATION: id1, id2] to back one claim with several sources.
    citation_pattern = re.compile(
        r"\[CITATION:\s*([a-f0-9\-]{36}(?:\s*,\s*[a-f0-9\-]{36})*)\]"
    )
    found_ids = [
        chunk_id.strip()
        for group in citation_pattern.findall(response_text)
        for chunk_id in group.split(",")
    ]

    # Build lookup map
    ctx_map = {str(ctx.chunk_id): ctx for ctx in contexts}
    citations = []
    seen = set()

    for chunk_id_str in found_ids:
        if chunk_id_str in seen or chunk_id_str not in ctx_map:
            continue
        seen.add(chunk_id_str)

        ctx = ctx_map[chunk_id_str]
        bbox_list = ctx.bbox or [0.0, 0.0, 100.0, 20.0]

        from app.models.schemas import BoundingBox

        citations.append(
            Citation(
                chunk_id=ctx.chunk_id,
                document_id=ctx.document_id,
                document_title=ctx.document_title,
                file_path=ctx.file_path,
                page_number=ctx.page_number,
                text_excerpt=ctx.text[:200],
                bbox=BoundingBox(
                    x0=bbox_list[0],
                    y0=bbox_list[1],
                    x1=bbox_list[2],
                    y1=bbox_list[3],
                    page_number=ctx.page_number,
                ),
                language_tag=ctx.language_tag,
                relevance_score=ctx.relevance_score,
            )
        )

    return citations
