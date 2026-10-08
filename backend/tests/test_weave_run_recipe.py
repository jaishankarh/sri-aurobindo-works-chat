"""Checks on the agent Run recipe (.weave/) and its synthetic seed data.

Pure file checks: no Docker, no database, no model. They skip when `.weave/` is absent
(e.g. when the tests run inside the backend image, whose build context is `backend/` only).
"""

import importlib.util
import json
import math
import re
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
WEAVE = ROOT / ".weave"
pytestmark = pytest.mark.skipif(not WEAVE.is_dir(), reason="no .weave/ directory beside backend/")

CHUNK_TYPES = {"prose", "poetry", "play", "table", "heading", "footnote", "correspondence"}
LANGUAGES = {"en", "fr", "sa"}
EMBEDDING_DIM = 1024  # backend/app/config.py: the pgvector column width the app is built for


def load_data() -> dict:
    return json.loads((WEAVE / "seed" / "data" / "001-corpus.json").read_text(encoding="utf-8"))


def load_stub():
    spec = importlib.util.spec_from_file_location("model_stub_server", WEAVE / "model_stub" / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_recipe() -> dict:
    yaml = pytest.importorskip("yaml")
    return yaml.safe_load((WEAVE / "compose.yaml").read_text(encoding="utf-8"))


# ---- seed data ----------------------------------------------------------------------------------

def test_seed_ids_are_unique_valid_uuids():
    data = load_data()
    for key in ("documents", "chunks", "sessions", "messages"):
        ids = [row["id"] for row in data[key]]
        assert ids, key
        assert len(set(ids)) == len(ids), key
        for i in ids:
            uuid.UUID(i)
    assert len({d["file_hash"] for d in data["documents"]}) == len(data["documents"])


def test_every_chunk_belongs_to_a_document_and_chunk_indexes_are_contiguous():
    data = load_data()
    doc_ids = {d["id"] for d in data["documents"]}
    per_doc: dict[str, list[int]] = {}
    for c in data["chunks"]:
        assert c["document_id"] in doc_ids
        assert c["language_tag"] in LANGUAGES
        assert c["chunk_type"] in CHUNK_TYPES
        assert len(c["bbox"]) == 4 and c["bbox"][0] < c["bbox"][2] and c["bbox"][1] < c["bbox"][3]
        per_doc.setdefault(c["document_id"], []).append(c["chunk_index"])
    for indexes in per_doc.values():
        assert sorted(indexes) == list(range(len(indexes)))


def test_the_three_corpus_languages_are_all_present_and_sanskrit_carries_its_transliteration():
    chunks = load_data()["chunks"]
    assert {c["language_tag"] for c in chunks} == LANGUAGES
    for c in chunks:
        if c["language_tag"] == "sa":
            assert re.search(r"[ऀ-ॿ]", c["text"])
            assert c["iast_text"] and c["sanskrit_glossary"]


def test_graph_entities_point_at_seeded_chunks_and_relations_at_seeded_entities():
    data = load_data()
    chunks = {c["id"]: c for c in data["chunks"]}
    entity_ids = {e["id"] for e in data["entities"]}
    assert len(entity_ids) == len(data["entities"]) >= 6
    for e in data["entities"]:
        assert chunks[e["chunk_id"]]["document_id"] == e["document_id"]
    assert data["relations"]
    for r in data["relations"]:
        assert r["source_id"] in entity_ids and r["target_id"] in entity_ids
        assert r["source_id"] != r["target_id"]


def test_chat_messages_belong_to_seeded_sessions_and_cite_seeded_chunks():
    data = load_data()
    sessions = {s["id"] for s in data["sessions"]}
    chunk_ids = {c["id"] for c in data["chunks"]}
    for m in data["messages"]:
        assert m["session_id"] in sessions
        for citation in m.get("citations", []):
            assert citation["chunk_id"] in chunk_ids


def test_seed_text_is_marked_synthetic_so_it_is_never_mistaken_for_the_corpus():
    for d in load_data()["documents"]:
        assert d["title"].startswith("[Synthetic]")


# ---- the model stand-in -------------------------------------------------------------------------

def test_stub_embeddings_have_the_apps_width_are_unit_length_and_deterministic():
    stub = load_stub()
    v = stub.embed("The soul aspires toward the light")
    assert len(v) == EMBEDDING_DIM
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, rel_tol=1e-6)
    assert v == stub.embed("The soul aspires toward the light")


def test_stub_embeddings_rank_a_related_passage_above_an_unrelated_one():
    stub = load_stub()
    chunks = load_data()["chunks"]
    en = [c for c in chunks if c["language_tag"] == "en"]
    query = stub.embed("what is surrender to the divine will")
    best = max(en, key=lambda c: sum(a * b for a, b in zip(query, stub.embed(c["text"]))))
    assert "surrender" in best["text"].lower()


def test_stub_chat_replies_are_what_each_app_step_expects():
    stub = load_stub()
    router = json.loads(stub.complete("... Respond ONLY with valid JSON ... \"needs_retrieval\": true ..."))
    assert router["needs_retrieval"] is True
    curator = json.loads(stub.complete("... \"selected_indices\": [1, 3, 4] ... [1] (source: vector) [2] ..."))
    assert curator["selected_indices"]
    cid = "11111111-2222-3333-4444-555555555555"
    answer = stub.complete(f"[SOURCE 1]\nChunk ID: {cid}\n---\ntext\n---\nProvide a thorough answer ... [CITATION:chunk_id]")
    assert f"[CITATION:{cid}]" in answer


# ---- the recipe ---------------------------------------------------------------------------------

def test_recipe_is_a_standalone_compose_file_with_the_required_services_and_no_gpu_or_local_model():
    recipe = load_recipe()
    services = recipe["services"]
    assert {"backend", "frontend", "postgres", "neo4j", "redis"} <= set(services)
    text = (WEAVE / "compose.yaml").read_text(encoding="utf-8")
    for forbidden in ("nvidia", "capabilities: [gpu]", "ollama/ollama", "container_name", "docker-compose.yml"):
        assert forbidden not in text, forbidden
    for name, svc in services.items():
        assert "ports" not in svc, f"{name} publishes a host port"
        assert "container_name" not in svc
        assert "deploy" not in svc, f"{name} has a resource reservation"
    env = services["backend"]["environment"]
    assert env["LLM_PROVIDER"] != "ollama" and env["EMBEDDING_PROVIDER"] != "bge_m3"
    assert "model-stub" in env["EMBEDDING_BASE_URL"] and "model-stub" in env["OPENAI_BASE_URL"]


def test_recipe_names_databases_seed_and_readiness_in_x_weave():
    recipe = load_recipe()
    block = recipe["x-weave"]
    assert set(block["readiness"]) == set(recipe["services"])
    assert {(d["service"], d["kind"]) for d in block["databases"]} == {("postgres", "postgres"), ("neo4j", "neo4j")}
    assert block["seed"]["service"] == "backend"
    assert "seed.py" in block["seed"]["command"]
    assert "/health" in str(block["readiness"]["backend"]["command"])


def test_recipe_holds_no_credential_beyond_throwaway_database_logins():
    recipe = load_recipe()
    text = (WEAVE / "compose.yaml").read_text(encoding="utf-8")
    assert not re.search(r"(sk-|AIza|ghp_|xox[bp]-|-----BEGIN)", text)
    for var in ("GEMINI_API_KEY", "ANTHROPIC_API_KEY"):
        assert var not in recipe["services"]["backend"].get("environment", {}), var
    assert recipe["x-weave"].get("secrets", []) == []
