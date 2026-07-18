"""
Dynamic graph schema generation via LLM.

For each document, samples representative chunks and prompts an LLM to:
1. Identify domain-relevant entity types (e.g., Deity, Philosophical_Concept)
2. Define relationship types between those entities
3. Output a JSON schema used by the extraction pass

This two-pass approach avoids a one-size-fits-all ontology that fails for
heterogeneous corpora (essays vs plays vs correspondences).
"""

import logging
import uuid
from typing import Optional

from app.core.llm.json_utils import parse_json_object
from app.models.schemas import DocumentGraphSchema, EntityType, RelationType

logger = logging.getLogger(__name__)

_SCHEMA_GEN_PROMPT = """You are an expert ontology designer for a multilingual philosophical and literary corpus.

Given the following text samples from a document, identify:
1. The most relevant ENTITY TYPES that appear in this text (3-8 types)
2. The most important RELATIONSHIP TYPES between those entities (3-8 types)

The corpus includes works by Sri Aurobindo and The Mother covering:
- Indian philosophy (Vedanta, Tantra, Yoga)
- French spiritual writings
- Poems, plays, and prose
- Correspondences and commentaries

Text samples:
---
{text_samples}
---

Respond ONLY with valid JSON matching this exact structure:
{{
  "entity_types": [
    {{
      "name": "EntityTypeName",
      "description": "Brief description",
      "examples": ["example1", "example2"]
    }}
  ],
  "relation_types": [
    {{
      "name": "RELATION_NAME",
      "description": "Brief description",
      "source_types": ["SourceType"],
      "target_types": ["TargetType"]
    }}
  ]
}}"""


async def generate_document_schema(
    document_id: uuid.UUID,
    sample_texts: list[str],
    llm_client=None,
) -> DocumentGraphSchema:
    """
    Generate a document-specific graph extraction schema using an LLM.

    Args:
        document_id: UUID of the document being processed.
        sample_texts: Representative text samples from the document.
        llm_client: LLM client instance (uses module-level default if None).

    Returns:
        DocumentGraphSchema with entity and relation type definitions.
    """
    if llm_client is None:
        from app.core.llm.client import get_llm_client
        llm_client = get_llm_client()

    combined_samples = "\n\n---\n\n".join(sample_texts[:5])
    prompt = _SCHEMA_GEN_PROMPT.format(text_samples=combined_samples[:3000])

    try:
        response_text = await llm_client.generate(prompt, max_tokens=1024)
        schema_data = parse_json_object(response_text, _default_schema())
    except Exception as e:
        logger.warning(f"Schema generation LLM call failed: {e}. Using default schema.")
        schema_data = _default_schema()

    return DocumentGraphSchema(
        document_id=document_id,
        entity_types=[EntityType(**et) for et in schema_data.get("entity_types", [])],
        relation_types=[RelationType(**rt) for rt in schema_data.get("relation_types", [])],
        generation_prompt=prompt,
    )


def _default_schema() -> dict:
    """
    Fallback schema for when LLM generation fails.

    Covers the most common entity and relationship types in the corpus.
    """
    return {
        "entity_types": [
            {
                "name": "PhilosophicalConcept",
                "description": "An abstract philosophical or spiritual idea",
                "examples": ["Supermind", "Maya", "Brahman", "Consciousness"],
            },
            {
                "name": "Deity",
                "description": "A divine being or aspect of the divine",
                "examples": ["Agni", "Indra", "Saraswati", "The Mother"],
            },
            {
                "name": "Person",
                "description": "A historical or mythological person",
                "examples": ["Sri Aurobindo", "Ramakrishna", "Arjuna"],
            },
            {
                "name": "Text",
                "description": "A scripture, poem, or written work",
                "examples": ["Rigveda", "Savitri", "Gita", "Arya"],
            },
            {
                "name": "SpiritualPractice",
                "description": "A spiritual discipline or method",
                "examples": ["Yoga", "Meditation", "Sadhana", "Tapas"],
            },
            {
                "name": "State",
                "description": "A state of consciousness or being",
                "examples": ["Samadhi", "Nirvana", "Turiya", "Overmind"],
            },
        ],
        "relation_types": [
            {
                "name": "MANIFESTS_AS",
                "description": "One concept manifests or expresses as another",
                "source_types": ["PhilosophicalConcept", "Deity"],
                "target_types": ["PhilosophicalConcept", "State"],
            },
            {
                "name": "LEADS_TO",
                "description": "One practice or state leads to another",
                "source_types": ["SpiritualPractice", "State"],
                "target_types": ["State", "PhilosophicalConcept"],
            },
            {
                "name": "AUTHORED_BY",
                "description": "A text was written by a person",
                "source_types": ["Text"],
                "target_types": ["Person"],
            },
            {
                "name": "DISCUSSES",
                "description": "A text or person discusses a concept",
                "source_types": ["Text", "Person"],
                "target_types": ["PhilosophicalConcept", "Deity"],
            },
            {
                "name": "EMBODIES",
                "description": "A person or deity embodies a concept",
                "source_types": ["Person", "Deity"],
                "target_types": ["PhilosophicalConcept", "State"],
            },
            {
                "name": "TRANSCENDS",
                "description": "One state or concept transcends another",
                "source_types": ["State", "PhilosophicalConcept"],
                "target_types": ["State", "PhilosophicalConcept"],
            },
        ],
    }
