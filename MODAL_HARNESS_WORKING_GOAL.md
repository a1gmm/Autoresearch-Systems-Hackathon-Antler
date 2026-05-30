# Modal Agent Harness Working Goal

Updated: 2026-05-30
Home repo: https://github.com/a1gmm/Autoresearch-Systems-Hackathon-Antler
Source studied: https://github.com/modal-labs/openai-agents-python-example
Status: local working goal for implementation

## Decision

Use Modal's OpenAI Agents SDK example as the harness pattern for our EHS research swarm.

We should not copy the Parameter Golf demo. We should copy the system shape:

- one orchestrator with persistent run state,
- dynamic subagents or workers created from scoped tasks,
- Modal-backed execution boundaries,
- async fan-out and result collection,
- quotas and timeouts,
- reusable setup snapshots where they save meaningful time,
- domain skills loaded only when a task needs them.

For our product, the harness must be artifact-driven and fail-closed. Workers collect evidence. The verifier decides whether evidence supports the claim.

## Working Goal

Build a runnable vertical slice where a seeded Southern California manufacturing scenario produces a defensible applicability matrix through a real agent-worker loop.

The slice is successful when:

1. Intake produces a typed `ScopePack`.
2. The orchestrator produces at least 5 `ResearchHypothesis` objects.
3. The orchestrator converts those hypotheses into bounded `ResearchTask` objects.
4. Modal runs 3-5 parallel research workers from those tasks.
5. Each worker returns an `EvidenceBundle` with source URL, fetched timestamp, source hash, quote, extracted claim, and task status.
6. The verifier rejects one intentionally overbroad or unsupported claim.
7. The orchestrator creates a `RepairTicket`.
8. One Modal repair worker reruns only the failed research step.
9. The verifier either passes the repaired bundle or marks it `Needs-review`.
10. The final matrix shows verified rows, at least one `Needs-review` row, citations, hashes, and verifier checks.

This is the demoable product promise:

> The system does not just summarize regulations. It creates scoped research tasks, runs them in parallel, checks whether each claim is actually supported, repairs bounded failures, and refuses to fake certainty.

## What We Borrow From Modal

### Orchestrator plus subagents

Modal's example keeps the orchestrator focused on planning, delegation, status, and result collection. Subagents do messy work in separate contexts.

Our version:

- `ScopeAgent` creates `ScopePack`.
- `OrchestratorAgent` creates hypotheses and research tasks.
- `ResearchWorker` runs in Modal for source fetch, extraction, and claim packaging.
- `VerifierAgent` checks authority, grounding, predicate math, and completeness.
- `SynthesisAgent` writes the matrix only after verification.

### Async fan-out

Modal's example starts subagent tasks without blocking, then waits for specific or first-completed results.

Our version:

- start one worker per `ResearchTask`,
- preserve the task ID through every result,
- stream trace events to the UI,
- collect failed tasks into repair candidates,
- enforce per-run and per-task budgets.

### Sandboxes and isolation

Modal's example uses sandboxes so agents work inside remote environments instead of the host machine.

Our version:

- workers may fetch public official sources,
- workers may run PDF extraction and hashing code,
- workers do not receive product secrets beyond the minimum needed,
- workers cannot write final determinations or memory.

### Quotas and timeouts

Modal's example includes GPU limits so agents cannot create unbounded expensive workers.

Our version:

- default max 5 workers for the hackathon slice,
- max 90 seconds per research task,
- max 2 repair attempts per failed claim,
- no GPU by default,
- max source count per task,
- hard terminal state of `Needs-review`.

### Snapshots

Modal's example snapshots prepared filesystems so later workers avoid repeated setup.

Our version:

- optional snapshot after installing source-fetch and PDF tooling,
- no snapshot dependency for the first slice,
- cached source fixtures remain available for demo reliability.

### Skills

Modal's example loads markdown skills for Parameter Golf context.

Our version:

- `skills/air_scaqmd.md`,
- `skills/stormwater_igp.md`,
- `skills/cupa_hmbp.md`,
- `skills/hazardous_waste_ca.md`,
- `skills/quote_grounding.md`.

Skills should guide source strategy and extraction discipline. They should not become trusted memory by themselves.

## What We Change For EHS

Modal's example is built for open-ended coding experiments. Our system is for defensible regulatory research, so we change the control contract:

- Replace free-form subagent summaries with typed artifacts.
- Keep final truth out of research workers.
- Require citations, exact quotes, dates, hashes, and verification checks.
- Treat missing facts and weak evidence as visible outputs, not hidden failures.
- Keep repair bounded.
- Keep memory writes gated by verification.

The rule remains:

> The orchestrator owns planning. The verifier owns truth.

## First Runnable Milestone

Name: `EHS Modal Worker Slice`

Input:

```json
{
  "facility": {
    "address": "Los Angeles County manufacturing facility",
    "jurisdiction_stack": ["SCAQMD", "California Water Boards", "Local CUPA"],
    "naics": "332813",
    "sic": "3471"
  },
  "project_change": {
    "description": "Adding a coating booth and storing a new hazardous liquid",
    "equipment": [{"kind": "coating_booth"}],
    "chemicals": [{"name": "flammable solvent", "quantity": 60, "unit": "gallons"}],
    "waste_streams": [{"description": "spent solvent", "kg_per_month": null}],
    "disturbance_acres": 0
  }
}
```

Expected worker fan-out:

1. SCAQMD permit trigger worker.
2. SCAQMD Rule 219 exemption worker.
3. Industrial stormwater SIC/NAICS worker.
4. HMBP hazardous liquid threshold worker.
5. Hazardous waste missing quantity worker.

Expected intentional failure:

- The HMBP worker initially extracts an overbroad claim:
  - Claim: "HMBP applies to all hazardous material storage."
  - Quote: source language that mentions threshold quantities.
- The verifier fails grounding because the quote does not support "all" storage.
- The repair worker extracts the threshold and compares it to 60 gallons.

Expected output:

- air permitting row: verified or needs-review with citation,
- Rule 219 row: considered, verified or needs-review,
- industrial stormwater row: verified or needs-review,
- HMBP row: repaired and verified,
- hazardous waste row: `Needs-review` because monthly quantity is missing.

## Implementation Order

1. Define Pydantic or Zod artifact schemas:
   - `ScopePack`
   - `ResearchHypothesis`
   - `ResearchTask`
   - `EvidenceBundle`
   - `VerificationVerdict`
   - `RepairTicket`
   - `ApplicabilityMatrix`
2. Build the local deterministic pipeline with cached source fixtures.
3. Implement `run_research_task(task)` as a Modal function or sandbox-backed worker.
4. Add parallel worker launch and result collection.
5. Add source fetch, extraction, quote capture, hash, and failure states.
6. Add verifier checks for authority, grounding, threshold math, and missing facts.
7. Add the bounded repair loop.
8. Add trace events for worker lifecycle and artifact transitions.
9. Add the matrix UI and evidence drawer.
10. Add golden evals from the seeded failure.

## Team Split

Backend/source owner:

- artifact schemas,
- source fixtures,
- source fetch/extract/hash,
- verifier checks,
- eval runner.

Orchestration/UI owner:

- Agents SDK loop,
- Modal worker adapter,
- task graph and repair loop,
- trace event stream,
- matrix and evidence drawer.

Shared:

- demo scenario,
- intentional failure fixture,
- final pitch,
- runbook for live demo versus cached replay.

## Acceptance Checklist

- [ ] `ScopePack` is visible in trace.
- [ ] At least 5 hypotheses are visible.
- [ ] Worker count is derived from task count, not hardcoded as a fixed team.
- [ ] Modal workers run in parallel for the live path.
- [ ] Cached replay can run without live network.
- [ ] Every successful evidence bundle has URL, fetched timestamp, quote, and hash.
- [ ] One verifier failure is visible.
- [ ] One repair ticket is visible.
- [ ] Repair does not restart the whole workflow.
- [ ] `Needs-review` appears when facts or evidence are incomplete.
- [ ] Final matrix contains verifier checks, not only citations.
- [ ] No sponsor credit codes, API keys, or customer data are committed.

## Non-Goals For This Slice

- Autonomous filing.
- Full compliance calendar.
- Multi-state support.
- More than 6-8 seeded regulatory programs.
- Live recursive skill generation.
- Unlimited worker spawning.
- GPU use.
- Trusted memory writes from unverified discovery.

## One-Sentence Build Goal

By the next working demo, a seeded EHS scenario should launch a bounded Modal-backed research swarm, repair one failed citation-grounding claim, and produce a source-backed applicability matrix that visibly fails closed.
