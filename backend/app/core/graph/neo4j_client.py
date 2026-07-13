"""
Neo4j driver lifecycle and schema setup.

Entities and relationships extracted from the corpus (philosophical concepts,
deities, persons, texts, and their relations) are stored as a native property
graph here — NOT as Postgres tables. This lets multi-hop traversal
(`graph_hops` setting) run as a single Cypher query instead of one SQL
round-trip per node per hop, which is what a hand-rolled BFS over relational
tables costs.

Schema:
  (:Entity {id, label, entity_type, description, chunk_id, document_id})
  (:Entity)-[:RELATES_TO {relation_type, weight}]->(:Entity)

A single generic RELATES_TO relationship (rather than a dynamic relationship
type per `relation_type`) is used because relation types are LLM-generated at
ingestion time and aren't known ahead of schema creation; the `relation_type`
property still lets Cypher filter/traverse by type when needed.
"""

import logging

from neo4j import AsyncDriver, AsyncGraphDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_driver: AsyncDriver | None = None


async def get_neo4j_driver() -> AsyncDriver:
    """Singleton async Neo4j driver (connection pool managed internally by the driver)."""
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )
    return _driver


async def close_neo4j_driver() -> None:
    """Close the driver and its connection pool. Call on application shutdown."""
    global _driver
    if _driver is not None:
        await _driver.close()
        _driver = None


async def init_neo4j_schema() -> None:
    """
    Create the uniqueness constraint and indexes graph_store.py depends on.

    Safe to call on every startup (all statements are idempotent via
    `IF NOT EXISTS`). The full-text index backs seed-entity lookup so it runs
    as a native Lucene query instead of a `LIKE '%...%'` table scan.
    """
    driver = await get_neo4j_driver()
    async with driver.session() as session:
        await session.run(
            "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS "
            "FOR (e:Entity) REQUIRE e.id IS UNIQUE"
        )
        await session.run(
            "CREATE FULLTEXT INDEX entity_search IF NOT EXISTS "
            "FOR (e:Entity) ON EACH [e.label, e.description]"
        )
        await session.run(
            "CREATE INDEX entity_document_id IF NOT EXISTS "
            "FOR (e:Entity) ON (e.document_id)"
        )
    logger.info("Neo4j schema initialized (constraint + indexes)")


async def write_graph_elements(entities: list[dict], relations: list[dict]) -> None:
    """
    Batch-upsert entities and relations extracted during ingestion.

    Uses UNWIND so an entire document's graph elements are written in two
    round-trips total, regardless of how many chunks they came from.
    """
    if not entities and not relations:
        return

    driver = await get_neo4j_driver()
    async with driver.session() as session:
        if entities:
            await session.run(
                """
                UNWIND $entities AS e
                MERGE (n:Entity {id: e.id})
                SET n.label = e.label,
                    n.entity_type = e.entity_type,
                    n.description = e.description,
                    n.chunk_id = e.chunk_id,
                    n.document_id = e.document_id
                """,
                entities=entities,
            )
        if relations:
            await session.run(
                """
                UNWIND $relations AS r
                MATCH (s:Entity {id: r.source_id})
                MATCH (t:Entity {id: r.target_id})
                MERGE (s)-[rel:RELATES_TO {relation_type: r.relation_type}]->(t)
                SET rel.weight = r.weight
                """,
                relations=relations,
            )


async def delete_document_graph(document_id: str) -> None:
    """Remove all graph entities (and their relationships) belonging to a document."""
    driver = await get_neo4j_driver()
    async with driver.session() as session:
        await session.run(
            "MATCH (e:Entity {document_id: $document_id}) DETACH DELETE e",
            document_id=document_id,
        )
