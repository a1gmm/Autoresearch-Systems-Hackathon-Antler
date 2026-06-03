"""Local HTTP server exposing the Python research runtime to the Next.js dev app.

The Next API route (/api/research/run) proxies to PYTHON_RESEARCH_RUN_SYNC_ENDPOINT.
In production that endpoint is a Modal deployment; for local manual testing this serves
the SAME request/response contract from your machine -- no Modal or Supabase required.

Run it (in a shell that has your OpenAI key):

    PYTHONPATH=src \\
    OPENAI_API_KEY=... \\
    RESEARCH_CORE_AGENT_MODEL=gpt-5-mini \\
    RESEARCH_CORE_REPAIR_MODEL=gpt-5.5 \\
    python -m research_core.local_server

Then point .env.local at it and restart `pnpm dev`:

    PYTHON_RESEARCH_RUN_SYNC_ENDPOINT=http://localhost:8787/run_sync

Endpoints:
    POST /run_sync   {project_description, demo_documents|documents, facility, ...} -> run result JSON
    GET  /get_run?run_id=...                                                        -> stored run JSON
    GET  /health                                                                    -> {"ok": true}
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from research_core.orchestrator import ResearchDeps, run_research_sync
from research_core.store import LocalRunStore


DEFAULT_PORT = 8787


def _load_env_local() -> None:
    """Load the repo's .env.local into os.environ (without overriding already-set vars) so
    the server picks up OPENAI_API_KEY and the model selection from the same file the Next
    app uses. Minimal parser -- no python-dotenv dependency."""
    for parent in [Path.cwd(), *Path(__file__).resolve().parents]:
        candidate = parent / ".env.local"
        if not candidate.is_file():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        return
# One store for the process so a /run_sync result is also retrievable via /get_run.
_STORE = LocalRunStore()


def _deps_mode() -> str:
    # Defaults to live (real agents). Set RESEARCH_CORE_DEPS_MODE=fake|offline for an
    # instant, free, deterministic smoke run (no LLM calls).
    mode = (os.environ.get("RESEARCH_CORE_DEPS_MODE") or "live").strip().lower()
    return mode if mode in {"fake", "offline"} else "live"


def _run_sync(payload: dict[str, Any]) -> dict[str, Any]:
    # Model selection (cheap worker / strong repair) is read from RESEARCH_CORE_AGENT_MODEL
    # / RESEARCH_CORE_REPAIR_MODEL by the orchestrator.
    result = run_research_sync(payload, deps=ResearchDeps(mode=_deps_mode()), store=_STORE)
    return result.model_dump(mode="json")


class _Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict[str, Any]) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 — http.server API
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(200, {"ok": True})
            return
        if parsed.path == "/get_run":
            run_id = (parse_qs(parsed.query).get("run_id") or [""])[0]
            record = _STORE.get_run(run_id) if run_id else None
            if record is None:
                self._send(404, {"error": f"run {run_id!r} not found"})
                return
            self._send(200, record)
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 — http.server API
        if urlparse(self.path).path not in {"/run_sync", "/run", "/start_run"}:
            self._send(404, {"error": "not found"})
            return
        try:
            length = int(self.headers.get("content-length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            payload = json.loads(raw or b"{}")
            if not isinstance(payload, dict):
                raise ValueError("request body must be a JSON object")
        except Exception as exc:  # noqa: BLE001
            self._send(400, {"error": f"invalid request body: {exc}"})
            return
        try:
            self._send(200, _run_sync(payload))
        except Exception as exc:  # noqa: BLE001 — surface as the run-failed contract
            self._send(
                500,
                {
                    "run_id": "run_failed",
                    "status": "failed",
                    "error": str(exc),
                    "exception_type": exc.__class__.__name__,
                },
            )

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter than default
        print(f"[local_server] {self.address_string()} {fmt % args}")


def serve(port: int | None = None) -> None:
    _load_env_local()
    resolved = port or int(os.environ.get("PYTHON_RESEARCH_LOCAL_PORT") or DEFAULT_PORT)
    worker = os.environ.get("RESEARCH_CORE_AGENT_MODEL") or "gpt-5.5 (default)"
    repair = os.environ.get("RESEARCH_CORE_REPAIR_MODEL") or "gpt-5.5 (default)"
    has_key = "set" if os.environ.get("OPENAI_API_KEY") else "MISSING"
    print(f"[local_server] research runtime on http://localhost:{resolved}", flush=True)
    print(f"[local_server]   worker model = {worker} | repair model = {repair} | OPENAI_API_KEY = {has_key}", flush=True)
    print(f"[local_server]   set .env.local: PYTHON_RESEARCH_RUN_SYNC_ENDPOINT=http://localhost:{resolved}/run_sync", flush=True)
    ThreadingHTTPServer(("127.0.0.1", resolved), _Handler).serve_forever()


if __name__ == "__main__":
    serve()
