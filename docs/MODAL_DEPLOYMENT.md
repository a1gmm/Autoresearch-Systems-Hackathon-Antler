# Modal Deployment

Deploy the Python research runtime from `src/research_core/modal_app.py`.

## Setup

```bash
modal setup
modal secret create permitpilot-openai OPENAI_API_KEY=sk-...
modal secret create permitpilot-research MODAL_RESEARCH_TOKEN=$(openssl rand -hex 24)
modal secret create permitpilot-supabase \
  SUPABASE_URL=https://<project>.supabase.co \
  SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
```

Optional local/file durable store for development only:

```bash
modal secret create permitpilot-store RESEARCH_CORE_STORE_ROOT=/tmp/permitpilot-runs
```

The Modal image declared in `src/research_core/modal_app.py` installs the Python
runtime dependencies: OpenAI Agents SDK, OpenAI client, Modal, Supabase, Pydantic,
HTTP/browser tooling, PDF/DOCX/spreadsheet readers, and Playwright.

## Deploy

```bash
modal deploy src/research_core/modal_app.py
```

The Modal app exposes:

| Function | Method | Purpose |
| --- | --- | --- |
| `run_sync` | POST | Run a Python research job synchronously |
| `start_run` | POST | Create queued run and spawn background `research_run` |
| `get_run` | GET | Return Python run state |
| `resume_run` | POST | Resume a stored Python run |
| `research_run` | background | Durable worker execution |

Modal functions default to `RESEARCH_CORE_DEPS_MODE=live`, which calls the
OpenAI Agents SDK researcher/repair agents with sandboxed regulatory tools. Use
`RESEARCH_CORE_DEPS_MODE=fake` only for local deterministic smoke tests.

## Next.js Environment

For synchronous demo runs:

```text
PYTHON_RESEARCH_RUN_SYNC_ENDPOINT=<Modal run_sync URL>
MODAL_RESEARCH_TOKEN=<same token>
```

For durable runs:

```text
PYTHON_RESEARCH_START_RUN_ENDPOINT=<Modal start_run URL>
PYTHON_RESEARCH_GET_RUN_ENDPOINT=<Modal get_run URL>
MODAL_RESEARCH_TOKEN=<same token>
```

Python/Modal also needs:

```text
OPENAI_API_KEY=<OpenAI key>
SUPABASE_URL=<Supabase project URL>
SUPABASE_SERVICE_ROLE_KEY=<Supabase service role key>
```

The Next.js shell no longer reads `USE_MODAL`, `MODAL_RESEARCH_ENDPOINT`, or
`RESEARCH_RUNTIME=durable`.

## Smoke

```bash
PATH=.venv/bin:$PATH npm run py:test
curl -s -X POST "$PYTHON_RESEARCH_RUN_SYNC_ENDPOINT" \
  -H "content-type: application/json" \
  -H "authorization: Bearer $MODAL_RESEARCH_TOKEN" \
  -d '{"project_description":"A coating shop stores 60 gal solvent."}'
```

Expect a JSON payload with `run_id`, terminal `status`, `result`, `evidence`,
and `verdicts`.
