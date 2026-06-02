# Durable Research Runtime

Durable research now belongs to the Python runtime. Next.js starts work through
the Python/Modal `start_run` endpoint and polls `get_run`; it does not use the
retired TypeScript durable planner/finalizer.

## Required Endpoints

| Name | Where | Purpose |
| --- | --- | --- |
| `PYTHON_RESEARCH_START_RUN_ENDPOINT` | Next server | Creates a queued Python run and spawns background work |
| `PYTHON_RESEARCH_GET_RUN_ENDPOINT` | Next server | Reads Python run state for UI polling |
| `MODAL_RESEARCH_TOKEN` | Next + Modal | Optional shared bearer token |
| `SUPABASE_URL` | Modal/Python | Supabase project URL for durable run records |
| `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_SERVICE_KEY` | Modal/Python | Service key for Python worker writes |

If `PYTHON_RESEARCH_START_RUN_ENDPOINT` is set without
`PYTHON_RESEARCH_GET_RUN_ENDPOINT`, `POST /api/research/run` fails fast. If
`PYTHON_RESEARCH_GET_RUN_ENDPOINT` is missing, `GET /api/research/run/:id` fails
fast. There is intentionally no TypeScript fallback.

## Flow

```text
POST /api/research/run
  -> Python start_run
  -> { run_id, status: "queued" }
  -> UI polls GET /api/research/run/:id
  -> Python get_run
  -> queued/running/.../done/needs_information/needs_review/failed
```

Python persistence uses `research_core.store.SupabaseRunStore` when
`SUPABASE_URL` and a service key are present. That is the production durable path
for Modal: `start_run` writes a queued run, background `research_run` updates the
same Supabase row/evidence records, and `get_run` can read the run from any
worker instance. `RESEARCH_CORE_STORE_ROOT` remains a local/dev JSON store; the
in-memory store is only a test fallback.

The Supabase migration keeps compatibility columns (`scope_pack`, `plan`,
`trace_events`, `determinations`, `report_markdown`) and also stores the full
Python record (`artifacts`, `verdicts`, `result`, `events`, `status_reason`).
Evidence rows use `(run_id, evidence_id)` so repair bundles for the same
hypothesis remain durable instead of overwriting the original research bundle.

## Verification

```bash
PATH=.venv/bin:$PATH npm run test -- app/api/research/run/__tests__/route.test.ts app/api/research/run/[id]/__tests__/route.test.ts
PATH=.venv/bin:$PATH npm run py:test
```
