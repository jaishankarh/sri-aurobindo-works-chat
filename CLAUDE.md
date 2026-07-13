# Project Brain: Sri Aurobindo & The Mother — Multilingual RAG Corpus Explorer

Multilingual RAG system for interrogating the Complete Works of Sri Aurobindo and The Mother
(English prose, French spiritual writings, Sanskrit/Devanagari, poetry and plays with
non-trivial spatial layout).

## Tech Stack
- **Frontend**: React 18 + Vite, TypeScript, Tailwind CSS, Zustand (state), react-pdf (PDF.js)
- **Backend**: Python 3.12+, FastAPI + uvicorn, Prefect 3 (background flows)
- **Storage**: PostgreSQL 16 + pgvector (documents, chunks, chat sessions/messages — dense +
  sparse retrieval) and Neo4j (knowledge graph entities/relations — multi-hop traversal via
  native Cypher instead of relational joins)
- **Streaming**: Redis Streams (Replay-then-Tail token delivery over WebSocket)
- **Embeddings**: BAAI/bge-m3 (dense + sparse, 100+ languages)
- **PDF parsing**: Docling for prose (hierarchical structure), custom PyMuPDF spatial-grid parser
  for poetry/plays (preserves indentation)
- **Local LLM inference**: Ollama

## Universal Code Conventions
- **Type Safety**: Enforce strict Python type hints; use `mypy` for validation.
- **FastAPI Standards**: Use Pydantic models (`response_model`) for request/response serialization.
  Use dependency injection (`Depends`) for DB sessions. Route handlers call service-layer functions
  in `app/services/`; they should not contain business logic directly.
- **Database Rules**: Documents, chunks (with pgvector embeddings), and chat sessions/messages
  live in PostgreSQL. Knowledge graph entities and relations live natively in Neo4j (see
  `app/core/graph/neo4j_client.py`) — never model graph nodes/edges as Postgres tables.
- **Error Handling**: Use custom FastAPI `HTTPException` handlers. Never bubble up raw SQL driver
  errors to the client.
- **Frontend State**: Keep `useChatStore` (token streaming), `usePDFStore` (canvas/citations), and
  `useSettingsStore` (persisted retrieval config) isolated — token streaming must never trigger PDF
  canvas re-renders.

## Common Development Commands
- **Install Backend Deps**: `pip install -r requirements.txt` (from `backend/`)
- **Run Backend**: `uvicorn app.main:app --reload --port 8000` (from `backend/`)
- **Run Frontend**: `npm run dev` (from `frontend/`, starts at `:5173`)
- **Run All Services**: `docker-compose up -d` (Postgres, Neo4j, Redis, Prefect, Ollama, backend, frontend)
- **Backend Tests**: `pytest tests/ -v` (from `backend/`)
- **Ingest Corpus**: `python scripts/ingest_corpus.py --pdf-dir /app/data/pdfs` (inside backend container)
- **Neo4j Browser**: `http://localhost:7474` (user `neo4j`, password from `NEO4J_PASSWORD`)

## Behavioral Constraints for Claude
1. **Coordinate Normalization**: PDF bounding boxes are bottom-left origin; PDF.js canvas is
   top-left origin. Keep the transform logic in `backend/app/core/parsing/spatial_parser.py` and
   `frontend/src/utils/coordinates.ts` in sync if either changes.
2. **Strict Architecture**: FastAPI route handlers (`app/api/routes/`) must not contain business
   logic — delegate to `app/services/`.
3. **Streaming Integrity**: Any change to the WebSocket relay or Redis Streams usage must preserve
   the Replay-then-Tail guarantee (zero token loss on reconnect) — see `app/services/streaming.py`.
4. **Zustand Isolation**: Never merge `useChatStore` and `usePDFStore` — this isolation is the
   documented fix for token-streaming performance.
5. **Graph Storage**: Knowledge graph entities/relations belong in Neo4j only
   (`app/core/graph/neo4j_client.py`, `app/core/retrieval/graph_store.py`). Never reintroduce
   Postgres `GraphNode`/`GraphEdge` tables — the whole point of Neo4j here is native multi-hop
   Cypher traversal instead of per-hop SQL round-trips.
