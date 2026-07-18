"""
Knowledge graph entity and relationship extractor.

Uses the dynamically generated document schema to prompt an LLM and extract
(entity, relation, entity) triples from each text chunk.
"""

import logging
import uuid
from typing import Optional

from app.core.llm.json_utils import parse_json_object
from app.models.schemas import DocumentGraphSchema

logger = logging.getLogger(__name__)

_EXTRACTION_PROMPT = """You are a knowledge graph extractor for philosophical and literary texts.

Using ONLY these entity types: {entity_types}
And ONLY these relation types: {relation_types}

Extract entities and relationships from this text. Focus on:
- Named philosophical concepts, deities, spiritual states
- Clear relationships between entities
- Do not hallucinate entities not present in the text

Text:
---
{text}
---

Respond ONLY with valid JSON:
{{
  "entities": [
    {{"label": "EntityName", "type": "EntityType", "description": "Brief description from text"}}
  ],
  "relations": [
    {{"source": "EntityName", "relation": "RELATION_TYPE", "target": "EntityName"}}
  ]
}}

If no entities are found, return {{"entities": [], "relations": []}}"""


async def extract_graph_elements(
    text: str,
    chunk_id: uuid.UUID,
    document_id: uuid.UUID,
    schema: DocumentGraphSchema,
    llm_client=None,
) -> tuple[list[dict], list[dict]]:
    """
    Extract graph nodes and edges from a single text chunk.

    Args:
        text: The text chunk to process.
        chunk_id: The UUID of the source chunk.
        document_id: The UUID of the source document.
        schema: The document-specific graph schema.
        llm_client: LLM client (uses default if None).

    Returns:
        (entities, relations) where each is a list of dicts ready for DB insertion.
    """
    if llm_client is None:
        from app.core.llm.client import get_llm_client
        llm_client = get_llm_client()

    entity_types_str = ", ".join(et.name for et in schema.entity_types)
    relation_types_str = ", ".join(rt.name for rt in schema.relation_types)

    prompt = _EXTRACTION_PROMPT.format(
        entity_types=entity_types_str,
        relation_types=relation_types_str,
        text=text[:2000],
    )

    try:
        response_text = await llm_client.generate(prompt, max_tokens=512)
        data = parse_json_object(response_text, {"entities": [], "relations": []})
    except Exception as e:
        logger.warning(f"Extraction failed for chunk {chunk_id}: {e}")
        return [], []

    raw_entities = data.get("entities", [])
    raw_relations = data.get("relations", [])

    # Validate entity types against schema
    valid_types = {et.name for et in schema.entity_types}
    entities = [
        {
            "id": str(uuid.uuid4()),
            "label": e.get("label", "Unknown")[:128],
            "entity_type": e.get("type", "PhilosophicalConcept")
            if e.get("type") in valid_types
            else "PhilosophicalConcept",
            "description": e.get("description", "")[:512],
            "chunk_id": str(chunk_id),
            "document_id": str(document_id),
        }
        for e in raw_entities
        if e.get("label")
    ]

    # Build a name→id map for linking relations
    entity_id_map = {e["label"]: e["id"] for e in entities}

    # Validate relation types against schema
    valid_relations = {rt.name for rt in schema.relation_types}
    relations = []
    for r in raw_relations:
        source_label = r.get("source")
        target_label = r.get("target")
        relation = r.get("relation", "DISCUSSES")

        if (
            source_label in entity_id_map
            and target_label in entity_id_map
            and relation in valid_relations
        ):
            relations.append(
                {
                    "id": str(uuid.uuid4()),
                    "source_id": entity_id_map[source_label],
                    "target_id": entity_id_map[target_label],
                    "relation_type": relation,
                    "weight": 1.0,
                }
            )

    return entities, relations
