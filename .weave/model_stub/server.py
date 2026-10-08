"""Stand-in for the language and embedding models, for the agent Run recipe only.

The chat backend already has provider switches: `LLM_PROVIDER=openai` (the OpenAI SDK reads
`OPENAI_BASE_URL`) and `EMBEDDING_PROVIDER=bge_m3_cloud` (an OpenAI-compatible /v1/embeddings
endpoint at `EMBEDDING_BASE_URL`). `.weave/compose.yaml` points both at this server, so the app
runs unchanged, with no GPU, no Ollama and no bge-m3 download. Nothing in the app is touched.

It is a test double, not a model:
  * embeddings: deterministic hashed bag-of-words vectors, EMBEDDING_DIM wide, unit length, so
    passages that share words are near each other and vector search returns sensible rows;
  * chat: canned replies in the shapes the app's router, curator and answer steps expect, the
    answer citing the first source passage it was given.

Standard library only (it runs in a bare python image).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DIM = int(os.environ.get("EMBEDDING_DIM", "1024"))
_WORD = re.compile(r"\w+", re.UNICODE)
_CHUNK_ID = re.compile(r"Chunk ID:\s*([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})")


def embed(text: str) -> list[float]:
    """Deterministic unit-length vector: each word hashes to a signed slot."""
    vec = [0.0] * DIM
    for word in _WORD.findall(text.lower()):
        digest = hashlib.sha256(word.encode("utf-8")).digest()
        slot = int.from_bytes(digest[:4], "big") % DIM
        vec[slot] += 1.0 if digest[4] & 1 else -1.0
    norm = math.sqrt(sum(x * x for x in vec))
    if norm == 0.0:
        vec[0] = 1.0
        return vec
    return [x / norm for x in vec]


def complete(prompt: str) -> str:
    """The canned reply for whichever step of the app sent `prompt`."""
    if '"needs_retrieval"' in prompt:  # router step
        return json.dumps({"needs_retrieval": True, "search_queries": [], "reasoning": "stub model"})
    if '"selected_indices"' in prompt:  # curator step
        return json.dumps({"selected_indices": [1, 2, 3, 4, 5]})
    match = _CHUNK_ID.search(prompt)
    if match:  # answer step
        return f"[Stub model answer, not a real model.] The first passage speaks to this [CITATION:{match.group(1)}]."
    return "{}"  # graph schema / extraction steps: valid JSON with nothing in it


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quiet; readiness polls are noisy
        pass

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}")

    def _json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._json({"status": "ok", "stub": True, "embedding_dim": DIM})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        path = self.path.split("?")[0]
        if path.endswith("/embeddings"):
            body = self._body()
            texts = body.get("input", [])
            texts = [texts] if isinstance(texts, str) else texts
            self._json({
                "object": "list",
                "model": body.get("model", "stub-embedding"),
                "data": [{"object": "embedding", "index": i, "embedding": embed(t)} for i, t in enumerate(texts)],
                "usage": {"prompt_tokens": 0, "total_tokens": 0},
            })
        elif path.endswith("/chat/completions"):
            self._chat(self._body())
        else:
            self._json({"error": "not found"}, 404)

    def _chat(self, body: dict) -> None:
        prompt = "\n".join(str(m.get("content", "")) for m in body.get("messages", []))
        reply = complete(prompt)
        model, cid, created = body.get("model", "stub-llm"), f"chatcmpl-{uuid.uuid4().hex}", int(time.time())
        if not body.get("stream"):
            self._json({
                "id": cid, "object": "chat.completion", "created": created, "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": reply}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            })
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def event(delta: dict, finish: str | None = None) -> None:
            chunk = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                     "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            data = f"data: {json.dumps(chunk)}\n\n".encode()
            self.wfile.write(f"{len(data):x}\r\n".encode() + data + b"\r\n")

        event({"role": "assistant", "content": ""})
        for word in re.findall(r"\S+\s*", reply):
            event({"content": word})
        event({}, "stop")
        done = b"data: [DONE]\n\n"
        self.wfile.write(f"{len(done):x}\r\n".encode() + done + b"\r\n0\r\n\r\n")
        self.wfile.flush()


def main() -> None:
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8080"))), Handler).serve_forever()


if __name__ == "__main__":
    main()
