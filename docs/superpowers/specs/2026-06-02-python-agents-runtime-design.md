# Python Agents Runtime Design

Date: 2026-06-02

## Goal

Replace the TypeScript research runtime with a Python-first research core built on the OpenAI Agents SDK. The Next.js app becomes an API/UI shell. Python owns planning, agent fanout, verification and repair, synthesis, durable Modal execution, Supabase persistence, scenario analysis, and Raindrop Workshop observability.

This is a big-bang runtime rewrite, not a gradual module-by-module port. The response contract may change if the UI shell is updated with it.

## Current Context

The current app is a Next.js/TypeScript EHS permit research system. TypeScript owns the main control loop in `src/lib/research`: scope planning, registry-driven task creation, worker dispatch, verification, repair, synthesis, durable run orchestration, and UI-facing types. Python exists today mainly as a Modal research worker in `src/lib/research/modal`, with a custom chat/tool loop rather than the OpenAI Agents SDK.

Important current invariants to preserve:

- Regulatory conclusions fail toward uncertainty instead of guessing.
- Registry-driven planning and recall floor prevent whole-program omissions.
- Evidence must be grounded in citable primary or high-authority sources.
- Verifier logic is deterministic and separate from model-produced findings.
- Durable runs use Modal and Supabase.
- Raindrop Workshop is used for run observability when configured.

## Architecture

Add a Python package at `src/research_core/` as the only authoritative research runtime.

Core modules:

- `models.py`: Pydantic models for intake, scope, programs, hypotheses, tasks, evidence, verdicts, repair tickets, determinations, scenarios, trace events, and persisted run state.
- `registry.py`: Python program registry. This becomes the source of truth for regulatory programs, hypotheses, authority sources, and trigger logic.
- `planner.py`: Converts scoped project facts and SDS handoff facts into coverage families, active programs, hypotheses, and task specs.
- `agents.py`: OpenAI Agents SDK agent definitions for scoping and regulatory research.
- `tools.py`: Deterministic tool implementations and policy enforcement.
- `documents.py`: PDF, DOCX, spreadsheet, and uploaded-document parsing helpers.
- `browser.py`: Browser/web-use helpers for dynamic agency pages and portals.
- `verifier.py`: Mechanical checks for quote grounding, authority, confidence, currency, and repair ticket creation.
- `orchestrator.py`: End-to-end runtime: scope, plan, fan out researchers, verify, repair, request information, generate scenarios, synthesize, apply recall floor, and persist.
- `synthesis.py`: Determination and report generation, including scenario comparison and distrust explanations.
- `store.py`: Supabase persistence and artifact indexing.
- `raindrop.py`: Raindrop Workshop trace helpers.
- `modal_app.py`: Modal functions and HTTP endpoints.

The old TypeScript research core becomes obsolete. Next.js keeps request validation, API proxying, polling/subscription UI, and presentation adapters. After the UI is wired to the Python contract, remove or quarantine the TypeScript planner, verifier, synthesis, durable runtime, and worker bridge.

## Modal And Supabase

The runtime stays on Modal with Supabase durable state.

Modal endpoints/functions:

- `start_run`: validates the request, creates or resumes a Supabase run, spawns durable work, and returns `{ run_id, status }`.
- `run_sync`: executes a complete run for local development, tests, or short demo paths.
- `research_run`: durable background function that owns orchestration and persistence.
- `resume_run`: continues a run after user-supplied information or accepted assumptions.
- `get_run`: Python-owned read endpoint that returns the canonical run payload for the UI.

Supabase persists:

- run status and input payload;
- scoped facts, missing facts, user-provided estimates, and scenario assumptions;
- plans, hypotheses, and selected programs;
- evidence bundles, source artifacts, browser artifacts, document extracts, and verifier verdicts;
- repair attempts, information requests, and retry history;
- final determinations, report markdown, scenario comparison, and trace events.

The schema can keep existing tables initially, but the Python `RunResult` should be stored as a JSON payload so the runtime contract can evolve without a migration for every model field. Evidence and artifacts should remain queryable as child rows for inspection.

## Data Flow

1. Next.js receives a project description and optional documents.
2. Next.js calls Modal `start_run` for durable mode or `run_sync` for local/demo mode.
3. Python creates or resumes a Supabase run and records the raw intake payload.
4. `ScopeAgent` parses intake and document handoff facts into a structured `ScopePack`.
5. The planner derives coverage families, active registry programs, hypotheses, and task specs.
6. The orchestrator fans out Agents SDK researcher runs in Modal.
7. Researcher agents use sandbox tools for web search, browser use, fetch, PDF/DOCX/table parsing, skill reading, chemical helpers, artifact writing, and finding submission.
8. The verifier checks each evidence bundle mechanically.
9. Weak evidence creates repair tickets. The orchestrator retries with alternate tools or sources.
10. Missing facts become structured information requests when a user answer is likely to unblock the run.
11. If the user does not know a fact, the runtime can generate scenario assumptions and continue in exploratory mode.
12. Synthesis creates determinations, scenario comparisons, distrust explanations, and report markdown.
13. The recall floor re-derives expected programs from the registry and adds review rows for missed programs.
14. Python writes final state to Supabase and emits Raindrop Workshop traces throughout.
15. Next.js renders the Python run result.

## OpenAI Agents SDK Usage

Use the OpenAI Agents SDK instead of the current hand-rolled chat/tool loop.

Agents:

- `ScopeAgent`: converts user intake, uploaded documents, accepted estimates, and scenario choices into structured scope facts.
- `ResearcherAgent`: a reusable regulatory researcher template parameterized by program, hypothesis, jurisdiction, task budget, and available tools.
- `RepairAgent`: specialized agent for repairing weak evidence with stricter instructions and the previous verifier verdict.
- `ScenarioAgent`: specialized agent that proposes low, expected, and high assumptions when the user does not know a missing fact.

Start with one generic `ResearcherAgent`; add family-specific agents only if testing shows the generic agent is too weak.

Agents SDK tracing should be correlated to `run_id`. Product-level traces still go to Supabase for the UI, while Raindrop Workshop receives the developer/evaluator trace.

## Tool Capability Model

The Python core exposes broad sandbox capabilities, but tools are role-scoped and audited.

Regulatory researcher tools:

- `web_search`: discover candidate official or high-authority sources. Search results are not evidence until fetched and grounded.
- `web_fetch`: fetch official web pages, PDFs, and source files with source metadata.
- `browser_use`: navigate dynamic agency pages, portals, search forms, and pages that plain fetch cannot inspect.
- `read_pdf`: extract text and metadata from PDFs, including page references when possible.
- `read_docx`: extract text from uploaded or fetched Word documents.
- `read_spreadsheet`: parse uploaded or fetched tables and threshold lists.
- `read_skill`: read bundled program and jurisdiction skills.
- `chemical_tools`: VOC, CAS, mixture, SDS, and threshold helpers.
- `write_artifact`: write run-scoped artifacts such as source extracts, normalized tables, screenshots, notes, and review packets.
- `submit_finding`: the only accepted path for model-produced evidence to enter verification.

Researcher agents can write run artifacts, not mutate the app repository or external user files. Repo edits, GitHub publication, email sending, Drive mutation, and similar side effects belong to a separate operator/maintenance capability layer.

Sandbox controls:

- per-run artifact directories;
- workspace-scoped artifact writes;
- URL and browser activity logging;
- source authority scoring and domain policy;
- model-call, browser-page, downloaded-byte, and runtime budgets;
- blocked tool exclusion by role;
- deterministic quote grounding before evidence acceptance;
- no autonomous external publishing.

The system may expose broader Codex-style tools through an operator gateway for maintenance tasks, but regulatory researchers receive only the subset needed for EHS research.

## Information Requests And Scenario Estimates

The runtime is persistent and recovery-oriented. It should not stop just because information is missing.

Use `needs_information` when a concrete user/project fact is likely to unblock the run. Persist structured requests:

```json
{
  "field": "chemicals.quantity",
  "question": "How many gallons of solvent will be stored on site?",
  "why_needed": "HMBP applicability depends on hazardous material quantity thresholds.",
  "blocks": ["ca-hmbp", "ca-apsa-spcc"]
}
```

When the user answers, resume the same run with accumulated artifacts and evidence.

User estimates and suggestions are valid inputs when the user expects estimate-based guidance. Classify fact provenance:

- `provided_exact`: user gives a known value.
- `provided_estimate`: user gives an approximate value, range, assumption, or best guess.
- `agent_suggested_user_accepted`: the agent proposes an assumption and the user accepts it.
- `agent_inferred`: the agent infers from context without explicit confirmation.
- `missing`: unresolved.

If the user does not know a fact, generate scenarios rather than stalling:

- `low`: conservative small-operation estimate;
- `expected`: typical estimate based on the described facility or project;
- `high`: upper-bound estimate that may trigger stricter requirements.

Each scenario must include the assumed value, why it is plausible, affected programs, conclusions that change across scenarios, and what evidence would confirm the fact.

Final output distinguishes:

- actual determinations grounded on known or accepted facts;
- estimate-based determinations grounded in law but dependent on assumptions;
- scenario comparisons when a fact is unknown.

The report should also suggest where to find missing facts, who usually knows them, and which fact matters most.

## Failure And Review Semantics

Statuses:

- `queued`
- `scoping`
- `needs_information`
- `planning`
- `researching`
- `verifying`
- `repairing`
- `synthesizing`
- `done`
- `needs_review`
- `failed`

Tool and evidence problems should trigger retries and alternate routes before review:

- fetch fails -> browser extraction;
- browser extraction fails -> search for official PDF or alternate agency page;
- PDF extraction fails -> OCR or alternate text extraction when available;
- ungrounded finding -> repair task with stricter evidence requirements;
- low confidence -> independent second pass or alternate source;
- missing project fact -> information request;
- user does not know -> scenario estimates.

`needs_review` is reached only after bounded retries, repair attempts, alternate tool paths, information requests, or scenario analysis still leave the agent unconfident.

Every `needs_review` determination must state:

- what was attempted;
- what evidence was found;
- what remains uncertain;
- why the agent does not trust the work;
- what a human should check next.

`failed` is reserved for operational failures that prevent a coherent run: missing configuration, Modal start failure, Supabase unavailable after retries, authentication failure, or corrupted persisted state. When possible, store a recovery instruction and checkpoint.

## Safety Invariants

- No ungrounded citation can produce a verified determination.
- No web search result can count as evidence until fetched and grounded.
- Browser screenshots alone cannot verify a requirement unless paired with extracted source text or a stored primary artifact.
- Model-produced findings always pass through deterministic verification.
- Researcher agents cannot mutate the app repo or external user files.
- External publication, email, comments, or filings require a separate operator approval path.
- Repair loops are bounded and visible.
- The recall floor remains mandatory and registry-derived.
- Estimate-based conclusions carry assumption provenance into the final report.

## Raindrop Workshop Observability

Raindrop Workshop is a required observability layer when configured. Runs must continue if Workshop is disabled or unreachable.

Emit traces correlated by `run_id` for:

- `scope`: intake parsing, missing facts, accepted estimates, and scenario creation;
- `planning`: coverage family activation, selected programs, hypotheses, and task specs;
- `research`: each Agents SDK researcher run, tool calls, browser/search/fetch/PDF/DOCX steps, and artifact writes;
- `verification`: quote grounding, authority checks, confidence scoring, and repair tickets;
- `repair`: redispatch attempts, alternate source strategies, information requests, and scenario fallback;
- `synthesis`: determinations, scenario comparison, recall floor, and report generation;
- `durable`: Supabase writes, resume checkpoints, and Modal fanout state.

Raindrop should capture metadata and artifact references, not secrets or uncontrolled raw private documents. Large documents, screenshots, source extracts, and tables belong in the artifact store with trace references.

The UI trace stream remains a simplified user-facing timeline. Raindrop Workshop is the developer and evaluator view for debugging agent behavior, tool use, retries, and confidence decisions.

## Testing

Python test coverage:

- `test_planner.py`: registry-driven planning, family activation, SDS handoff activation, scenario activation, and recall expectations.
- `test_agents_tools.py`: tool permissions, search/fetch/browser fallback, PDF/DOCX/table parsing, artifact writes, quote grounding, and budget enforcement.
- `test_verifier.py`: verbatim quote checks, authority checks, low-confidence repair tickets, and untrusted evidence rejection.
- `test_orchestrator.py`: full lifecycle, retries, information requests, scenario estimates, repair loops, final synthesis, and `needs_review` distrust explanations.
- `test_modal_app.py`: endpoint payload validation, Supabase persistence mapping, resumable run state, and operational failure handling.
- `test_raindrop.py`: trace emission when configured and no-op behavior when unavailable.
- `test_golden_runs.py`: representative EHS scenarios converted from the existing Vitest/eval cases.

TypeScript tests should shrink to shell responsibilities:

- API route proxy behavior;
- polling and subscription behavior;
- UI mapping from Python response to components;
- report rendering and scenario display.

## Migration Plan

1. Add Python package, Pydantic models, and test harness.
2. Implement Python registry, planner, verifier, synthesis, and scenario models.
3. Implement Agents SDK scoping and researcher agents with sandbox tools.
4. Implement Modal endpoints and Supabase persistence.
5. Add Raindrop Workshop tracing for the Python runtime.
6. Replace Next.js research routes with thin Modal/Supabase shell routes.
7. Update UI state/selectors/components for the new Python run contract.
8. Convert golden EHS tests and add Python end-to-end coverage.
9. Remove obsolete TypeScript research core after the Python runtime and UI pass.
10. Update README, durable runtime docs, Modal deployment docs, and tool catalog docs.

## Acceptance Criteria

- A complete research run executes from Python.
- OpenAI Agents SDK is used for scoping and researcher flows.
- Modal/Supabase durable mode can start, resume, and complete runs.
- Next.js can start and render Python-owned runs.
- Researchers can use sandboxed web search, browser use, PDF/DOCX/table parsing, artifact writes, skills, and chemical helpers.
- Missing facts can become resumable information requests.
- Unknown facts can become scenario estimates and suggestions.
- User-provided estimates and accepted assumptions are valid inputs with provenance.
- `needs_review` appears only after retries, repair, information requests, or scenario analysis still leave distrust.
- Every `needs_review` result clearly states why the agent does not trust the work.
- No verified determination can come from ungrounded evidence.
- Recall floor remains registry-derived and mandatory.
- Raindrop Workshop traces exist for every configured run and are non-blocking when unavailable.
