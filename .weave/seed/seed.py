"""Seed command of the agent Run recipe: synthetic data into Postgres and Neo4j.

Run inside the `backend` service (`x-weave.seed` in .weave/compose.yaml), after every service is
ready, so the app has already created its own tables, pgvector extension and Neo4j schema. This
script uses the app's own models, embedding path (which the recipe points at the model stand-in)
and graph writer, so it needs no copy of the schema.

Seed scripts are append-only and tracked in the databases themselves: running the command again
applies only what is missing. To change the data, add `002-...json` to SCRIPTS; never edit one
that has run.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"
SCRIPTS = ["001-corpus"]  # applied in this order


def load(script: str) -> dict:
    return json.loads((DATA_DIR / f"{script}.json").read_text(encoding="utf-8"))


async def seed_postgres(script: str, data: dict) -> bool:
    from sqlalchemy import text

    from app.core.embeddings import embed_texts
    from app.database import AsyncSessionLocal
    from app.models.database import ChatMessage, ChatSession, Chunk, Document

    name = f"{script}:postgres"
    async with AsyncSessionLocal() as session:
        await session.execute(text(
            "CREATE TABLE IF NOT EXISTS weave_seed_applied "
            "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        ))
        done = await session.execute(text("SELECT 1 FROM weave_seed_applied WHERE name = :n"), {"n": name})
        if done.first():
            return False

        for d in data["documents"]:
            session.add(Document(id=uuid.UUID(d["id"]), **{k: v for k, v in d.items() if k != "id"}))
        await session.flush()

        # Through the app's own embedding path: the recipe points it at the model stand-in.
        embeddings = await embed_texts([c["text"] for c in data["chunks"]])
        for c, emb in zip(data["chunks"], embeddings):
            fields = {k: v for k, v in c.items() if k not in ("id", "document_id")}
            session.add(Chunk(
                id=uuid.UUID(c["id"]),
                document_id=uuid.UUID(c["document_id"]),
                dense_embedding=[float(x) for x in emb["dense"]],
                sparse_embedding={str(k): float(v) for k, v in emb.get("sparse", {}).items()},
                **fields,
            ))
        for s in data["sessions"]:
            session.add(ChatSession(id=uuid.UUID(s["id"]), settings=s["settings"]))
        await session.flush()
        for m in data["messages"]:
            session.add(ChatMessage(
                id=uuid.UUID(m["id"]), session_id=uuid.UUID(m["session_id"]),
                role=m["role"], content=m["content"], citations=m["citations"], is_complete=m["is_complete"],
            ))
        await session.flush()
        await session.execute(text("INSERT INTO weave_seed_applied (name) VALUES (:n)"), {"n": name})
        await session.commit()
    return True


async def seed_neo4j(script: str, data: dict) -> bool:
    from app.core.graph import get_neo4j_driver, init_neo4j_schema, write_graph_elements

    name = f"{script}:neo4j"
    await init_neo4j_schema()
    driver = await get_neo4j_driver()
    async with driver.session() as session:
        found = await (await session.run("MATCH (s:SeedApplied {name: $n}) RETURN s", n=name)).single()
        if found:
            return False
    await write_graph_elements(data["entities"], data["relations"])
    async with driver.session() as session:
        await session.run("MERGE (:SeedApplied {name: $n})", n=name)
    return True


async def main() -> int:
    from app.core.graph import close_neo4j_driver
    from app.database import close_db

    try:
        for script in SCRIPTS:
            data = load(script)
            pg = await seed_postgres(script, data)
            graph = await seed_neo4j(script, data)
            print(f"seed {script}: postgres {'applied' if pg else 'already applied'}, "
                  f"neo4j {'applied' if graph else 'already applied'}")
    finally:
        await close_neo4j_driver()
        await close_db()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
