---
name: fullstack-dev
description: Workflow for full-stack features touching FastAPI, Postgres/pgvector, Neo4j, Redis streaming, and the React frontend of the RAG corpus explorer.
triggers:
  - "add a new retrieval feature"
  - "add a new API endpoint"
  - "wire up a new frontend feature to the backend"
---

# Full-Stack Integration Workflow

When adding a feature that spans backend and frontend, follow this sequence:

## Step 1: Schema & Data Layer
- Add/modify SQLAlchemy models for relational data (documents, chunks, sessions — see
  `backend/app/models/database.py`).
- If the feature touches knowledge-graph entities/relations, model them in Neo4j
  (`app/core/graph/neo4j_client.py`), not as new Postgres tables — see rule 3 in
  `.claude/rules/backend.md`.
- If it touches retrieval, decide whether it affects the dense path (`vector_store.py`), sparse
  path (BM25), or graph path (`graph_store.py`), and how it should be weighted in RRF (`hybrid.py`).

## Step 2: FastAPI Routing & Service Layer
- Add the endpoint to the appropriate router in `app/api/routes/` (`chat.py`, `documents.py`,
  `settings.py`) with an explicit Pydantic `response_model`.
- Put the actual logic in `app/services/`, not the route handler.
- If the feature is long-running (ingestion, a new RAG flow), implement it as a Prefect flow in
  `app/workers/prefect_flows.py` rather than blocking the request.
- If it streams tokens, reuse the Redis Replay-then-Tail pattern in `app/services/streaming.py` —
  don't invent a second streaming mechanism.

## Step 3: Frontend Client Synchronization
- Match TypeScript types in `frontend/src/types/index.ts` to the FastAPI response model.
- Add data fetching via a hook in `frontend/src/hooks/` (see `useRAGQuery.ts`, `useWebSocket.ts`).
- Put any new UI state in the correct Zustand store — chat-token state in `useChatStore`, PDF/citation
  state in `usePDFStore`, persisted config in `useSettingsStore`. Never merge these stores.

## Step 4: Validation
- Add/extend backend tests under `backend/tests/` (`pytest tests/ -v`).
- If the feature touches PDF bounding boxes, verify against `test_coordinates.py`'s roundtrip checks.
- If it touches streaming, verify against `test_streaming.py`'s reconnect/zero-loss checks.
