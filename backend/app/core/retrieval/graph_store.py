"""
Knowledge graph traversal for multi-hop philosophical reasoning.

Implements BFS/DFS graph traversal over GraphNode/GraphEdge tables
to find related entities and their source chunks.
"""

import logging
import uuid
from collections import deque
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import GraphEdge, GraphNode, Chunk, Document
from app.models.schemas import RetrievedContext

logger = logging.getLogger(__name__)


async def find_entity_by_label(
    session: AsyncSession,
    query: str,
    document_filter: Optional[list[uuid.UUID]] = None,
    top_k: int = 5,
) -> list[GraphNode]:
    """Find graph nodes whose label or description matches the query string."""
    stmt = select(GraphNode).where(
        GraphNode.label.ilike(f"%{query}%")
        | GraphNode.description.ilike(f"%{query}%")
    )
    if document_filter:
        stmt = stmt.where(GraphNode.document_id.in_(document_filter))
    stmt = stmt.limit(top_k)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def traverse_graph(
    session: AsyncSession,
    seed_node_ids: list[uuid.UUID],
    max_hops: int = 2,
    max_nodes: int = 20,
) -> list[GraphNode]:
    """
    BFS traversal of the knowledge graph starting from seed nodes.

    Returns all reachable nodes within max_hops, deduplicating by node ID.
    """
    visited: set[uuid.UUID] = set(seed_node_ids)
    queue: deque[tuple[uuid.UUID, int]] = deque(
        (nid, 0) for nid in seed_node_ids
    )
    all_nodes: list[GraphNode] = []

    while queue and len(all_nodes) < max_nodes:
        node_id, depth = queue.popleft()

        # Fetch the node
        result = await session.execute(
            select(GraphNode).where(GraphNode.id == node_id)
        )
        node = result.scalar_one_or_none()
        if node:
            all_nodes.append(node)

        if depth >= max_hops:
            continue

        # Fetch outgoing edges
        edge_result = await session.execute(
            select(GraphEdge).where(GraphEdge.source_id == node_id)
        )
        edges = list(edge_result.scalars().all())

        for edge in edges:
            if edge.target_id not in visited:
                visited.add(edge.target_id)
                queue.append((edge.target_id, depth + 1))

        # Also traverse incoming edges (undirected for context retrieval)
        in_edge_result = await session.execute(
            select(GraphEdge).where(GraphEdge.target_id == node_id)
        )
        in_edges = list(in_edge_result.scalars().all())

        for edge in in_edges:
            if edge.source_id not in visited and depth < max_hops:
                visited.add(edge.source_id)
                queue.append((edge.source_id, depth + 1))

    return all_nodes


async def get_chunks_for_nodes(
    session: AsyncSession,
    nodes: list[GraphNode],
) -> list[RetrievedContext]:
    """
    Retrieve source chunks associated with a list of graph nodes.

    Each node has an optional chunk_id pointing back to the original text.
    """
    contexts: list[RetrievedContext] = []
    seen_chunks: set[uuid.UUID] = set()

    for node in nodes:
        if node.chunk_id is None or node.chunk_id in seen_chunks:
            continue

        seen_chunks.add(node.chunk_id)

        result = await session.execute(
            select(Chunk, Document)
            .join(Document, Chunk.document_id == Document.id)
            .where(Chunk.id == node.chunk_id)
        )
        row = result.first()
        if row is None:
            continue

        chunk, document = row
        contexts.append(
            RetrievedContext(
                chunk_id=chunk.id,
                document_id=document.id,
                document_title=document.title,
                file_path=document.file_path,
                text=chunk.text,
                page_number=chunk.page_number,
                bbox=chunk.bbox,
                language_tag=chunk.language_tag,
                relevance_score=0.7,  # graph traversal has fixed base score
                retrieval_source="graph",
            )
        )

    return contexts


async def graph_retrieve(
    session: AsyncSession,
    query: str,
    max_hops: int = 2,
    document_filter: Optional[list[uuid.UUID]] = None,
    top_k: int = 5,
) -> list[RetrievedContext]:
    """
    Full graph retrieval pipeline:
    1. Find seed nodes matching the query
    2. Traverse graph up to max_hops
    3. Fetch associated chunks as context

    Returns retrieved context chunks from the knowledge graph.
    """
    seed_nodes = await find_entity_by_label(
        session, query, document_filter=document_filter, top_k=top_k
    )

    if not seed_nodes:
        logger.debug(f"No graph nodes found for query: {query[:50]}")
        return []

    seed_ids = [n.id for n in seed_nodes]
    all_nodes = await traverse_graph(
        session, seed_ids, max_hops=max_hops, max_nodes=top_k * 4
    )

    return await get_chunks_for_nodes(session, all_nodes)
