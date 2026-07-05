"""
Document ingestion service.

Orchestrates the full ingestion pipeline:
1. Parse PDF (classify + extract chunks with bboxes)
2. Language detection + Sanskrit transliteration
3. Embedding generation (dense + sparse)
4. Store chunks in PostgreSQL
5. Generate dynamic graph schema
6. Extract knowledge graph nodes and edges
7. Store graph in PostgreSQL
"""

import hashlib
import logging
import uuid
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embeddings import embed_texts
from app.core.graph import extract_graph_elements, generate_document_schema
from app.core.language import process_chunk_language
from app.core.parsing import classify_and_parse
from app.core.parsing.models import ParsedChunk
from app.models.database import Chunk, Document, GraphEdge, GraphNode
from app.models.schemas import IngestionStatus

logger = logging.getLogger(__name__)


def _hash_file(file_path: str | Path) -> str:
    """Compute SHA256 hash of a file for deduplication."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


async def ingest_document(
    session: AsyncSession,
    file_path: str | Path,
    title: Optional[str] = None,
    author: Optional[str] = None,
    force_reingest: bool = False,
    progress_callback: Optional[Callable[[IngestionStatus], None]] = None,
    llm_client=None,
) -> Document:
    """
    Full ingestion pipeline for a single PDF document.

    Args:
        session: Async DB session (should NOT be committed inside; caller commits)
        file_path: Path to the PDF file
        title: Optional document title (defaults to filename)
        author: Optional author name
        force_reingest: Re-process even if already ingested
        progress_callback: Optional callback receiving IngestionStatus updates
        llm_client: LLM client for graph extraction

    Returns:
        The created or updated Document ORM object.
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"PDF not found: {file_path}")

    def _progress(status: str, progress: float, message: str = ""):
        if progress_callback:
            progress_callback(
                IngestionStatus(status=status, progress=progress, message=message)
            )

    _progress("parsing", 0.0, f"Reading {file_path.name}")
    file_hash = _hash_file(file_path)
    doc_title = title or file_path.stem.replace("_", " ").replace("-", " ").title()

    # Check for existing document
    from sqlalchemy import select
    existing = await session.execute(
        select(Document).where(Document.file_hash == file_hash)
    )
    existing_doc = existing.scalar_one_or_none()

    if existing_doc and not force_reingest:
        logger.info(f"Document already ingested: {doc_title} (id={existing_doc.id})")
        _progress("done", 1.0, "Already ingested")
        return existing_doc

    # Create or update document record
    if existing_doc:
        doc = existing_doc
    else:
        doc = Document(
            title=doc_title,
            author=author,
            file_path=str(file_path),
            file_hash=file_hash,
        )
        session.add(doc)
        await session.flush()  # get doc.id

    _progress("parsing", 0.1, "Classifying and parsing PDF layout")

    # Parse PDF into chunks
    parsed_chunks: list[ParsedChunk] = list(classify_and_parse(file_path))
    doc.page_count = max((c.page_number for c in parsed_chunks), default=0)

    _progress("embedding", 0.3, f"Embedding {len(parsed_chunks)} chunks")

    # Batch embed all chunk texts
    texts = []
    for chunk in parsed_chunks:
        lang, iast_text, glossary = process_chunk_language(chunk.text)
        chunk.language_tag = lang
        chunk.iast_text = iast_text
        chunk.sanskrit_glossary = glossary

        # Augment text with Sanskrit glossary for better multilingual embeddings
        embed_text = chunk.text
        if glossary:
            gloss_str = " | ".join(f"{k}: {v}" for k, v in list(glossary.items())[:5])
            embed_text = f"{chunk.text} [GLOSSARY: {gloss_str}]"
        texts.append(embed_text)

    embedding_results = await embed_texts(texts, return_sparse=True)

    _progress("storing", 0.5, "Storing chunks in database")

    # Persist chunks
    chunk_records: list[Chunk] = []
    sample_texts: list[str] = []

    for i, (parsed, emb) in enumerate(zip(parsed_chunks, embedding_results)):
        dense_vec = emb["dense"].tolist()
        sparse_vec = {str(k): float(v) for k, v in emb.get("sparse", {}).items()}

        db_chunk = Chunk(
            document_id=doc.id,
            text=parsed.text,
            page_number=parsed.page_number,
            bbox=parsed.bbox.to_list() if parsed.bbox else None,
            language_tag=parsed.language_tag,
            chunk_type=parsed.chunk_type.value,
            iast_text=parsed.iast_text,
            sanskrit_glossary=parsed.sanskrit_glossary or None,
            dense_embedding=dense_vec,
            sparse_embedding=sparse_vec,
            chunk_index=i,
        )
        session.add(db_chunk)
        chunk_records.append(db_chunk)

        # Sample for graph schema generation
        if i < 10 and len(parsed.text) > 100:
            sample_texts.append(parsed.text)

    await session.flush()

    _progress("graphing", 0.7, "Generating dynamic graph schema")

    # Generate document-specific graph schema
    schema = await generate_document_schema(
        document_id=doc.id,
        sample_texts=sample_texts,
        llm_client=llm_client,
    )

    _progress("graphing", 0.8, "Extracting knowledge graph")

    # Extract graph from each chunk (limit to first 50 for speed)
    node_id_map: dict[str, GraphNode] = {}

    for chunk_record in chunk_records[:50]:
        entities, relations = await extract_graph_elements(
            text=chunk_record.text,
            chunk_id=chunk_record.id,
            document_id=doc.id,
            schema=schema,
            llm_client=llm_client,
        )

        # Persist nodes
        for ent in entities:
            node = GraphNode(
                id=uuid.UUID(ent["id"]),
                document_id=doc.id,
                chunk_id=chunk_record.id,
                label=ent["label"],
                entity_type=ent["entity_type"],
                description=ent.get("description", ""),
            )
            session.add(node)
            node_id_map[ent["id"]] = node

        await session.flush()

        # Persist edges
        for rel in relations:
            if rel["source_id"] in node_id_map and rel["target_id"] in node_id_map:
                edge = GraphEdge(
                    id=uuid.UUID(rel["id"]),
                    source_id=uuid.UUID(rel["source_id"]),
                    target_id=uuid.UUID(rel["target_id"]),
                    relation_type=rel["relation_type"],
                    weight=rel.get("weight", 1.0),
                )
                session.add(edge)

    doc.is_processed = True
    _progress("done", 1.0, f"Ingested {len(parsed_chunks)} chunks, {len(node_id_map)} graph nodes")

    return doc
