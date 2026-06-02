# PermitPilot - Python EHS Research Runtime

PermitPilot is an Environmental, Health & Safety research system that turns a
project description into a defensible regulatory applicability report. The
research runtime now lives in Python under `src/research_core/`; the Next.js app
is an API/UI shell that proxies to Python/Modal endpoints and renders Python run
records.

Scope today: California EHS research with jurisdiction resolution, registry
planning, discovery candidates, sandboxed source/document/browser tools,
verification and repair, missing-fact scenarios, synthesis, and Raindrop
Workshop tracing.

## Runtime Shape

```text
Next.js UI/API shell
  -> POST /api/research/run
     -> PYTHON_RESEARCH_RUN_SYNC_ENDPOINT or PYTHON_RESEARCH_START_RUN_ENDPOINT
  -> GET /api/research/run/:id
     -> PYTHON_RESEARCH_GET_RUN_ENDPOINT
  -> Python src/research_core/modal_app.py
     -> orchestrator -> planner/discovery -> agents/tools -> verifier/repair -> synthesis/store
```

The removed TypeScript research runtime is no longer a fallback. If the Python
endpoints are not configured, the API returns a clear configuration error.

## Key Modules

| Path | Role |
| --- | --- |
| `src/research_core/models.py` | Pydantic runtime contract |
| `src/research_core/planner.py` | Registry-driven planning |
| `src/research_core/agents.py` | OpenAI Agents SDK agent definitions |
| `src/research_core/tools.py` | Sandboxed regulatory web/document/file tools |
| `src/research_core/verifier.py` | Verification, repair tickets, distrust reasons |
| `src/research_core/scenarios.py` | Missing-fact estimates and suggestions |
| `src/research_core/orchestrator.py` | End-to-end run lifecycle |
| `src/research_core/modal_app.py` | Modal endpoints and durable worker functions |
| `src/lib/research/types.ts` | UI-facing ResearchRun contract |
| `src/lib/research/pythonRunAdapter.ts` | Python payload to UI shape adapter |
| `src/lib/research/skills/**` | Markdown skill assets read by the Python runtime |

## Environment

Use one POST path:

| Name | Purpose |
| --- | --- |
| `PYTHON_RESEARCH_RUN_SYNC_ENDPOINT` | Modal/FastAPI sync endpoint for demo/local runs |
| `PYTHON_RESEARCH_START_RUN_ENDPOINT` | Modal async start endpoint for durable runs |
| `PYTHON_RESEARCH_GET_RUN_ENDPOINT` | Modal get_run endpoint; required for async starts and GET polling |
| `MODAL_RESEARCH_TOKEN` | Optional shared bearer token sent as `Authorization` and `x-research-token` |
| `OPENAI_API_KEY` | Intake and live Python Agents SDK calls |
| `RESEARCH_CORE_STORE_ROOT` | Optional local durable JSON store root for Python tests/dev |

## Running Locally

```bash
npm install
npm run dev
npm run test
npm run py:test
npm run typecheck
npm run eval
```

Deploy/smoke Modal with:

```bash
modal deploy src/research_core/modal_app.py
./scripts/test-modal.sh
```

## Invariants

- Python owns planning, fanout, verification/repair, synthesis, durable worker
  execution, and tracing.
- Next.js never fabricates research results and no longer falls back to the old
  TypeScript runtime.
- Missing facts produce information requests and, when the user does not know,
  low/expected/high scenarios with provenance.
- `needs_review` appears only when the verifier still does not trust the work
  after bounded repair/information attempts, and the response explains why.
- Treat final determinations as human-review research support, not legal advice
  or autonomous filing.
