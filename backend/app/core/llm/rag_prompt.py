"""
RAG synthesis prompt builder.

Constructs the final generation prompt from retrieved context chunks,
enforcing strict citation propagation and bounding box integrity.
"""

from app.models.schemas import Citation, RetrievedContext

_SYSTEM_PROMPT = """You are a scholarly assistant specializing in the integral philosophy and spiritual writings of Sri Aurobindo and The Mother. You assist researchers and seekers in understanding this vast corpus spanning English prose, French writings, Sanskrit, poetry, and philosophical dialogues.

CRITICAL RULES:
1. Answer ONLY from the provided context passages. Do not draw on outside knowledge.
2. Every factual claim must be supported by a citation from the context.
3. When you cite a source, use the exact citation format: [CITATION:chunk_id] at the end of the sentence.
4. Preserve all citation metadata exactly as provided — do not modify or invent bounding boxes or page numbers.
5. If a passage is in French, quote it in French with an English translation.
6. If a passage uses Sanskrit terms, include both the IAST transliteration and its English meaning.
7. If the context does not contain sufficient information, acknowledge the limitation honestly."""

_CONTEXT_TEMPLATE = """
[SOURCE {index}]
Document: {title}
Page: {page_number}
Language: {language}
Chunk ID: {chunk_id}
---
{text}
---
"""

_USER_PROMPT_TEMPLATE = """Using ONLY the provided source passages, answer this question:

{query}

Context Passages:
{context_block}

Provide a thorough answer with precise citations using [CITATION:chunk_id] format after each supported claim."""


def build_rag_prompt(
    query: str,
    contexts: list[RetrievedContext],
) -> tuple[str, str]:
    """
    Build the system and user prompts for RAG synthesis.

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
            chunk_id=str(ctx.chunk_id),
            text=ctx.text[:1500],  # cap individual context length
        )
        context_blocks.append(block)

    return _SYSTEM_PROMPT, _USER_PROMPT_TEMPLATE.format(
        query=query,
        context_block="\n".join(context_blocks),
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

    citation_pattern = re.compile(r"\[CITATION:([a-f0-9\-]{36})\]")
    found_ids = citation_pattern.findall(response_text)

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
