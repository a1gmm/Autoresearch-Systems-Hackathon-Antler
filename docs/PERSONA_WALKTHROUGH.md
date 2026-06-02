# Persona Walkthrough

Run this against the local Next.js app after configuring Python research
endpoints.

## Before You Start

```bash
npm run dev
```

Set either:

```text
PYTHON_RESEARCH_RUN_SYNC_ENDPOINT=<Python run_sync endpoint>
```

or:

```text
PYTHON_RESEARCH_START_RUN_ENDPOINT=<Python start_run endpoint>
PYTHON_RESEARCH_GET_RUN_ENDPOINT=<Python get_run endpoint>
```

Optional:

```text
MODAL_RESEARCH_TOKEN=<shared token>
```

Without Python endpoints, the UI should show a clear failed run configuration
message. It should not run the retired TypeScript research runtime.

## Persona A: Coating Shop

1. Open the app.
2. Run a project such as: "A Los Angeles County coating shop adds a coating
   booth and stores 60 gal flammable solvent."
3. Check that the graph, trace stream, applicability matrix, and report cards
   are populated from Python run data.

Pass criteria: every trusted row has evidence/provenance, and `needs_review`
rows explain why the work is not trusted.

## Persona B: Missing Quantity

1. Run: "A coating shop stores solvent, unknown quantity."
2. Check the Missing Facts panel.

Pass criteria: the run reaches `needs_information` with a concrete question for
`chemicals.quantity`. The system does not guess.

## Persona C: User Does Not Know

1. Run a missing-quantity project with `user_does_not_know` through the API or a
   payload-enabled client.
2. Check the Missing Facts panel and scenario comparison.

Pass criteria: low/expected/high scenarios appear with provenance such as
`agent_inferred`, and the report remains explicit about assumptions.

## Persona D: Durable Polling

1. Configure `PYTHON_RESEARCH_START_RUN_ENDPOINT` and
   `PYTHON_RESEARCH_GET_RUN_ENDPOINT`.
2. Start a run from the UI.
3. Watch the status progress from `queued` to a terminal status.

Pass criteria: transient GET failures do not strand the UI; polling resumes
until `done`, `needs_information`, `needs_review`, or `failed`.
