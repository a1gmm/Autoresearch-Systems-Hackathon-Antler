# Modal Deployment

Deploy the Python research runtime from `src/research_core/modal_app.py`.

## Setup

```bash
modal setup
modal secret create permitpilot-openai OPENAI_API_KEY=sk-...
modal secret create permitpilot-research MODAL_RESEARCH_TOKEN=$(openssl rand -hex 24)
```

Optional local/file durable store:

```bash
modal secret create permitpilot-store RESEARCH_CORE_STORE_ROOT=/tmp/permitpilot-runs
```

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

The Next.js shell no longer reads `USE_MODAL`, `MODAL_RESEARCH_ENDPOINT`, or
`RESEARCH_RUNTIME=durable`.

## Smoke

```bash
npm run py:test
curl -s -X POST "$PYTHON_RESEARCH_RUN_SYNC_ENDPOINT" \
  -H "content-type: application/json" \
  -H "authorization: Bearer $MODAL_RESEARCH_TOKEN" \
  -d '{"project_description":"A coating shop stores 60 gal solvent."}'
```

Expect a JSON payload with `run_id`, terminal `status`, `result`, `evidence`,
and `verdicts`.
