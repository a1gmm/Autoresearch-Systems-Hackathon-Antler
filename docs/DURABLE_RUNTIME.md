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

Python persistence currently uses `research_core.store.LocalRunStore` by
default, with `RESEARCH_CORE_STORE_ROOT` for local durable JSON records. The
Modal app is shaped so a Supabase-backed Python store can sit behind the same
`start_run` and `get_run` endpoints without changing the Next.js shell.

## Verification

```bash
npm run test -- app/api/research/run/__tests__/route.test.ts app/api/research/run/[id]/__tests__/route.test.ts src/lib/ui/__tests__/store.test.ts
npm run py:test
```
