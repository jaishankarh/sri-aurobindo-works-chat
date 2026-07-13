# Sri Aurobindo & The Mother — Multilingual RAG Corpus Explorer

A highly heterogeneous, multilingual Retrieval-Augmented Generation (RAG) system for interrogating the Complete Works of Sri Aurobindo and The Mother.

## Overview

Standard RAG pipelines fail on this corpus because it combines:
- **Complex spatial layouts** — poetry stanzas (Savitri), plays (Perseus the Deliverer), indented stage directions
- **Mixed languages** — English prose, French spiritual writings (The Mother's Agenda), Devanagari/IAST Sanskrit
- **Multi-hop philosophical reasoning** — concepts span decades of texts and require graph traversal

This system solves each problem through purpose-built architecture:

| Problem | Solution |
|---------|----------|
| Poetry / play layouts | Spatial grid parser (PyMuPDF) preserving exact indentation |
| Prose / essays | Hierarchical parser (Docling) preserving heading structure |
| Sanskrit text | `indic-transliteration` → IAST + glossary injection |
| Cross-lingual retrieval | `BAAI/bge-m3` shared 100+-language vector space |
| Keyword + semantic blend | Reciprocal Rank Fusion (RRF) with tunable α coefficient |
| Multi-hop reasoning | Dynamic GraphRAG in Neo4j with document-specific LLM-generated schemas |
| Reconnect resilience | Redis Streams "Replay-then-Tail" pattern (zero token loss) |
| PDF canvas performance | Decoupled Zustand stores (chat tokens ≠ PDF re-renders) |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Frontend (React + Vite + Zustand)                                       │
│  ┌─────────────────────┐   ┌──────────────────────────────────────────┐ │
│  │  Chat Interface     │   │  PDF Viewer (PDF.js)                     │ │
│  │  useChatStore       │   │  usePDFStore (ISOLATED)                  │ │
│  │  Token streaming    │   │  Highlight layer (bbox coordinate xform) │ │
│  └──────────┬──────────┘   └──────────────────────────────────────────┘ │
│             │ WebSocket (Replay-then-Tail)                               │
└─────────────┼───────────────────────────────────────────────────────────┘
              │
┌─────────────▼───────────────────────────────────────────────────────────┐
│  FastAPI Backend                                                          │
│  ┌─────────────────┐  ┌──────────────────┐  ┌──────────────────────┐   │
│  │ /api/v1/chat/ws │  │  Prefect Worker  │  │  Prefect UI :4200    │   │
│  │  WebSocket      ├──►  rag_query_flow  │  │  Observability       │   │
│  │  relay          │  │  retrieve → LLM  │  └──────────────────────┘   │
│  └────────┬────────┘  └───────┬──────────┘                             │
│           │                   │                                          │
│           ▼                   ▼                                          │
│  ┌────────────────┐  ┌────────────────────────────────────────────────┐│
│  │  Redis Streams │  │  Hybrid Retrieval                              ││
│  │  XADD / XRANGE │  │  Dense (pgvector) + Sparse (BM25) + Graph      ││
│  │  Replay-then-  │  │  Fused via RRF (configurable α)                ││
│  │  Tail pattern  │  └──────┬─────────────────────────────────┬───────┘│
│  └────────────────┘         │                                 │        │
│                   ┌─────────▼──────────┐          ┌───────────▼──────┐ │
│                   │  PostgreSQL +      │          │  Neo4j           │ │
│                   │  pgvector          │          │  Entities /      │ │
│                   │  Chunks / Sessions │          │  Relations       │ │
│                   │  Documents         │          │  (multi-hop      │ │
│                   │                    │          │  Cypher query)   │ │
│                   └────────────────────┘          └──────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Tech Stack

### Backend
| Component | Technology | Purpose |
|-----------|------------|---------|
| Web framework | FastAPI + uvicorn | Async REST + WebSocket |
| Orchestration | Prefect 3 | Background task observability |
| Streaming | Redis Streams | Replay-then-Tail token delivery |
| Vector store | PostgreSQL + pgvector | Dense ANN search |
| Graph store | Neo4j | Entity/relation storage, native multi-hop Cypher traversal |
| Embeddings | BAAI/bge-m3 | Dense + sparse, 100+ languages |
| PDF parsing (prose) | Docling (IBM) | Hierarchical structure |
| PDF parsing (poetry/plays) | PyMuPDF spatial grid | Whitespace preservation |
| Sanskrit | indic-transliteration | Devanagari → IAST |
| Language detection | langdetect | EN / FR / SA routing |

### Frontend
| Component | Technology | Purpose |
|-----------|------------|---------|
| UI framework | React 18 + Vite | SPA |
| State: chat | Zustand `useChatStore` | Token streaming (isolated) |
| State: PDF | Zustand `usePDFStore` | Canvas state (isolated) |
| State: settings | Zustand `useSettingsStore` | Persisted retrieval config |
| PDF rendering | react-pdf (PDF.js) | In-browser PDF display |
| Highlights | Custom `HighlightLayer` | Bounding-box overlays |
| Styling | Tailwind CSS | Utility-first styles |

---

## Quick Start

### Prerequisites

- Docker & Docker Compose
- [Ollama](https://ollama.ai) installed locally (for local LLM inference)

### 1. Clone and configure

```bash
git clone <repo>
cd sri-aurobindo-works-chat
cp .env.example .env
# Edit .env if needed (API keys, model names, etc.)
```

### 2. Start services

```bash
docker-compose up -d
```

This starts:
- PostgreSQL 16 with pgvector at `:5432`
- Neo4j 5 at `:7687` (Bolt) / `:7474` (Browser UI)
- Redis 7 at `:6379`
- Prefect server at `:4200`
- Ollama at `:11434`
- FastAPI backend at `:8000`
- React frontend at `:3000`

### 3. Pull an LLM model

```bash
docker exec -it aurobindo_ollama ollama pull llama3.2
```

### 4. Download the corpus PDFs

```bash
# From the backend directory:
docker exec -it aurobindo_backend python scripts/download_pdfs.py --output-dir /app/data/pdfs
```

> **Note:** The ashram website may require manual downloads for some volumes.
> Place PDFs in `data/pdfs/Sri_Aurobindo/` and `data/pdfs/The_Mother/`.

### 5. Ingest the corpus

```bash
docker exec -it aurobindo_backend python scripts/ingest_corpus.py --pdf-dir /app/data/pdfs
```

### 6. Open the UI

Visit [http://localhost:3000](http://localhost:3000)

---

## Development Setup

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start with hot reload:
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev  # starts at http://localhost:5173
```

### Tests

```bash
cd backend
pytest tests/ -v
```

**Test coverage:**
- `test_coordinates.py` — 17 tests: bounding box Y-axis inversion, scaling, roundtrip accuracy
- `test_streaming.py` — 9 tests: Redis Replay-then-Tail zero-loss recovery
- `test_retrieval.py` — 17 tests: RRF scoring, alpha weighting, multilingual context
- `test_language.py` — 12 tests: Language detection, Sanskrit transliteration, glossary

---

## Key Design Decisions

### Coordinate Normalization

PDF bounding boxes use a bottom-left origin (y=0 at page bottom). PDF.js canvas uses a top-left origin (y=0 at page top). The transformation is:

```
canvas_top    = (page_height - bbox.y1) × scale_y
canvas_bottom = (page_height - bbox.y0) × scale_y
canvas_left   = bbox.x0 × scale_x
canvas_right  = bbox.x1 × scale_x
```

Implemented in `backend/app/core/parsing/spatial_parser.py` (extraction) and `frontend/src/utils/coordinates.ts` (display).

### Replay-then-Tail

When a user reconnects after a network disconnect, the WebSocket endpoint:
1. **REPLAY**: `XRANGE stream_key {last_seen_id} +` — reads all missed tokens from Redis
2. **TAIL**: `XREAD BLOCK 1000 streams stream_key {cursor}` — subscribes to new tokens

This guarantees 100% token delivery regardless of connection interruptions.

### RRF Hybrid Retrieval

```
score(doc) = α × rrf_dense(rank) + (1-α) × rrf_sparse(rank) + 0.3 × rrf_graph(rank)
rrf(rank) = 1 / (60 + rank)
```

The α slider in the UI controls the dense/sparse balance. `α=1.0` gives pure bge-m3 semantic search; `α=0.0` gives pure BM25 keyword matching.

### Zustand Store Isolation

Three separate stores prevent cross-contamination of state updates:
- `useChatStore` — updated on every LLM token (~50/s during streaming)
- `usePDFStore` — only updated when citations are clicked or pages change
- `useSettingsStore` — persisted to localStorage; updated only on user interaction

This isolation is the critical performance measure: token streaming must not cause PDF canvas re-renders.

---

## API Reference

### REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/api/v1/documents/` | List all ingested documents |
| `POST` | `/api/v1/documents/ingest` | Queue a PDF for ingestion |
| `DELETE` | `/api/v1/documents/{id}` | Delete a document |
| `POST` | `/api/v1/chat/query` | Synchronous RAG query |
| `GET` | `/api/v1/chat/sessions/{id}/messages` | Get chat history |
| `POST` | `/api/v1/settings/sessions` | Create new session |
| `PUT` | `/api/v1/settings/sessions/{id}` | Update session settings |

### WebSocket

`ws://localhost:8000/api/v1/chat/ws/{session_id}`

**Send (query):**
```json
{
  "type": "query",
  "query": "What is Sri Aurobindo's concept of the Supermind?",
  "settings": { "alpha": 0.7, "top_k": 5, "graph_hops": 2, "language_filter": ["en", "fr", "sa"] }
}
```

**Send (reconnect):**
```json
{ "type": "reconnect", "last_seen_id": "1234567890-0" }
```

**Receive (streaming):**
```json
{ "type": "status", "data": { "status": "retrieving" } }
{ "type": "token", "data": "The ", "idx": 0 }
{ "type": "citation", "data": { "citations": [...] } }
{ "type": "complete", "data": { "token_count": 342 } }
```

---

## Corpus Notes

The corpus includes:
- **Sri Aurobindo's Complete Works** (35+ volumes): The Life Divine, Synthesis of Yoga, Savitri, Essays on the Gita, Letters on Yoga, plays, poetry, translations
- **The Mother's Collected Works** (17 volumes in French): L'Agenda de Mère, Questions et Réponses, Entretiens, etc.

Both collections are published by the Sri Aurobindo Ashram Trust and available at:
- https://www.sriaurobindoashram.org/sriaurobindo/writings.php
- https://www.sriaurobindoashram.org/mother/oeuvres.php
