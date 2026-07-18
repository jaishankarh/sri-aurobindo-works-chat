"""
Shared JSON-from-LLM-text parsing.

LLMs asked to "respond only with JSON" still commonly wrap the object in
markdown code fences, or add stray text around it. This strips fences and
extracts the outermost {...} object rather than trusting the response to be
bare, valid JSON — used anywhere a plain-text LLM call needs a structured
result (graph schema generation, entity extraction, agentic router/curator).
"""

import json
import logging
import re

logger = logging.getLogger(__name__)

_FENCE_START_RE = re.compile(r"```(?:json)?\s*")
_FENCE_END_RE = re.compile(r"```\s*$")


def parse_json_object(text: str, default: dict) -> dict:
    """Extract and parse the outermost {...} JSON object from LLM text output."""
    text = _FENCE_START_RE.sub("", text).strip()
    text = _FENCE_END_RE.sub("", text).strip()

    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return default

    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON object from LLM response")
        return default
