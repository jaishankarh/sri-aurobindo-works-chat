"""
Neo4j-backed knowledge graph retrieval for multi-hop philosophical reasoning.

Seed-entity lookup uses Neo4j's full-text index (native Lucene search), and
traversal runs as a single variable-length Cypher pattern match — replacing a
prior implementation that stored nodes/edges as Postgres tables and walked
them with a hand-rolled Python BFS (one SQL round-trip per node per hop).
Chunk text itself still lives in Postgres, so the final step joins the graph
hit's `chunk_id` back to the `chunks` table.
"""

import logging
import re
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.graph.neo4j_client import get_neo4j_driver
from app.models.database import Chunk, Document
from app.models.schemas import RetrievedContext

logger = logging.getLogger(__name__)

_MAX_ALLOWED_HOPS = 5  # hard ceiling; the hop count is spliced into the Cypher pattern


def _sanitize_fulltext_query(query: str) -> str:
    """Strip Lucene special characters and build a fuzzy OR query from terms."""
    terms = re.sub(r"[^\w\s]", " ", query).split()
    if not terms:
        return query
    return " OR ".join(f"{t}~" for t in terms[:12])


async def find_seed_entities(
    query: str,
    document_filter: Optional[list[uuid.UUID]] = None,
    top_k: int = 5,
) -> list[dict]:
    """Find seed entities via Neo4j's full-text index over label + description."""
    driver = await get_neo4j_driver()
    doc_ids = [str(d) for d in document_filter] if document_filter else None

    async with driver.session() as session:
        result = await session.run(
            """
            CALL db.index.fulltext.queryNodes('entity_search', $search_text)
            YIELD node, score
            WHERE $doc_ids IS NULL OR node.document_id IN $doc_ids
            RETURN node.id AS id, node.label AS label, node.entity_type AS entity_type,
                   node.description AS description, node.chunk_id AS chunk_id,
                   node.document_id AS document_id
            ORDER BY score DESC
            LIMIT $top_k
            """,
            search_text=_sanitize_fulltext_query(query),
            doc_ids=doc_ids,
            top_k=top_k,
        )
        return [record.data() async for record in result]


async def traverse_graph(
    seed_ids: list[str],
    max_hops: int = 2,
    max_nodes: int = 20,
    document_filter: Optional[list[uuid.UUID]] = None,
) -> list[dict]:
    """
    Single-query variable-length traversal from seed nodes.

    Neo4j does not allow parameterizing the hop bound inside a relationship
    pattern, so it's spliced in directly — safe here since it's an int clamped
    to _MAX_ALLOWED_HOPS, never raw user input.

    document_filter is enforced on the final node set (seed AND neighbors),
    not just on seed selection upstream in find_seed_entities — a hop can
    otherwise land on an entity from a document outside the user's current
    selection even when the seed itself was correctly scoped. Neo4j can't
    constrain intermediate/end nodes inside a variable-length pattern without
    APOC, so this filters the traversal's result set instead of the pattern
    itself; the corpus-sized graph makes that cheap enough to matter little.
    """
    if not seed_ids:
        return []

    hops = max(1, min(max_hops, _MAX_ALLOWED_HOPS))
    doc_ids = [str(d) for d in document_filter] if document_filter else None
    driver = await get_neo4j_driver()

    async with driver.session() as session:
        result = await session.run(
            f"""
            MATCH (seed:Entity) WHERE seed.id IN $seed_ids
            OPTIONAL MATCH (seed)-[:RELATES_TO*1..{hops}]-(neighbor:Entity)
            WITH collect(DISTINCT seed) + collect(DISTINCT neighbor) AS nodes
            UNWIND nodes AS n
            WITH DISTINCT n
            WHERE n IS NOT NULL
              AND ($doc_ids IS NULL OR n.document_id IN $doc_ids)
            RETURN n.id AS id, n.label AS label, n.entity_type AS entity_type,
                   n.description AS description, n.chunk_id AS chunk_id,
                   n.document_id AS document_id
            LIMIT $max_nodes
            """,
            seed_ids=seed_ids,
            max_nodes=max_nodes,
            doc_ids=doc_ids,
        )
        return [record.data() async for record in result]


async def get_chunks_for_nodes(
    session: AsyncSession,
    nodes: list[dict],
) -> list[RetrievedContext]:
    """Resolve graph hits back to their source chunk text/bbox in Postgres."""
    seen_chunks: set[str] = set()
    chunk_ids: list[uuid.UUID] = []

    for node in nodes:
        cid = node.get("chunk_id")
        if cid and cid not in seen_chunks:
            seen_chunks.add(cid)
            chunk_ids.append(uuid.UUID(cid))

    if not chunk_ids:
        return []

    result = await session.execute(
        select(Chunk, Document)
        .join(Document, Chunk.document_id == Document.id)
        .where(Chunk.id.in_(chunk_ids))
    )

    return [
        RetrievedContext(
            chunk_id=chunk.id,
            document_id=document.id,
            document_title=document.title,
            file_path=document.file_path,
            text=chunk.text,
            page_number=chunk.page_number,
            bbox=chunk.bbox,
            language_tag=chunk.language_tag,
            chunk_type=chunk.chunk_type,
            relevance_score=0.7,  # graph traversal has a fixed base score
            retrieval_source="graph",
        )
        for chunk, document in result.all()
    ]


async def graph_retrieve(
    session: AsyncSession,
    query: str,
    max_hops: int = 2,
    document_filter: Optional[list[uuid.UUID]] = None,
    top_k: int = 5,
) -> list[RetrievedContext]:
    """
    Full graph retrieval pipeline:
    1. Find seed entities matching the query (Neo4j full-text index)
    2. Traverse the graph up to max_hops (single Cypher query)
    3. Fetch associated chunks as context (Postgres)
    """
    if max_hops <= 0:
        return []

    try:
        seed_entities = await find_seed_entities(
            query, document_filter=document_filter, top_k=top_k
        )
        if not seed_entities:
            logger.debug(f"No graph entities found for query: {query[:50]}")
            return []

        seed_ids = [e["id"] for e in seed_entities]
        all_nodes = await traverse_graph(
            seed_ids,
            max_hops=max_hops,
            max_nodes=top_k * 4,
            document_filter=document_filter,
        )
        return await get_chunks_for_nodes(session, all_nodes)
    except Exception as e:
        logger.warning(f"Graph retrieval failed, continuing without graph context: {e}")
        return []
