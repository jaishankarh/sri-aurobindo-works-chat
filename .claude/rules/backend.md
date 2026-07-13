---
globs: "backend/**/*"
---
# FastAPI, PostgreSQL/pgvector & Neo4j Architecture Rules

## 1. FastAPI Rules
- **Async/Sync Boundaries**: Use `async def` for route handlers interacting with async clients
  (DB sessions, Redis). Use standard `def` for heavy blocking compute (parsing, embeddings) or
  offload it to a Prefect flow/worker instead of the request path.
- **Pydantic Validation**: Every API route must explicitly define a `response_model` via a Pydantic
  schema to filter out internal system properties.
- **Layering**: Route handlers in `app/api/routes/` must not contain business logic — they call
  into `app/services/` (`chat.py`, `ingestion.py`, `streaming.py`).

## 2. PostgreSQL + pgvector Rules
- Documents, chunks (with pgvector embeddings), and chat sessions/messages live in PostgreSQL.
- Vector similarity search uses pgvector via `app/core/retrieval/vector_store.py`.
- Always use parameterized queries or SQLAlchemy session methods. Raw string concatenation is
  banned to prevent SQL injection.
- Hybrid retrieval fuses dense (pgvector), sparse (BM25), and graph results via Reciprocal Rank
  Fusion (`app/core/retrieval/hybrid.py`) — don't bypass RRF with ad hoc score blending.

## 3. Neo4j Rules
- Knowledge graph entities and relations (`:Entity` nodes, `:RELATES_TO` edges) live natively in
  Neo4j — see `app/core/graph/neo4j_client.py` and `app/core/retrieval/graph_store.py`. Do not
  reintroduce them as Postgres tables; the point of Neo4j here is that multi-hop traversal
  (`graph_hops` setting) runs as a single Cypher query instead of one SQL round-trip per node per hop.
- Seed-entity lookup uses the `entity_search` full-text index (`db.index.fulltext.queryNodes`),
  not a `CONTAINS`/`ILIKE` scan.
- Use parameterized Cypher (`session.run(query, param=value)`) — never string-interpolate
  user-supplied query text into Cypher. The one exception is the hop-count bound in
  `traverse_graph`, which is spliced in because Neo4j can't parameterize a relationship pattern's
  range — it's safe only because that value is an int clamped server-side, never raw user input.
- Entity nodes must carry `document_id` and `chunk_id` properties so results can be filtered by
  the document filter setting and joined back to chunk text in Postgres.

## 4. Redis Streams Rules
- Token streaming uses the Replay-then-Tail pattern (`app/services/streaming.py`): `XRANGE` to
  replay missed tokens on reconnect, then `XREAD BLOCK` to tail new ones. Any change to the
  WebSocket relay must preserve zero-token-loss on reconnect.

## 5. Prefect Rules
- Long-running RAG queries and ingestion run as Prefect flows (`app/workers/prefect_flows.py`),
  not inline in the request handler, so they're observable via the Prefect UI (`:4200`).
