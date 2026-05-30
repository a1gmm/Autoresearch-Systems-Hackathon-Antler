# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

EHS Permit-Navigator — an AI-native research swarm that turns a Southern California facility change into a defensible regulatory applicability matrix.

Home repo: https://github.com/a1gmm/Autoresearch-Systems-Hackathon-Antler

Demo claim: given a SoCal manufacturing change, the agent swarm determines applicable EHS obligations, proves each row with current source evidence, and visibly fails closed when evidence is incomplete.

## Tech Stack

- **OpenAI Agents SDK** — agent control loop, structured outputs, guardrails, traces
- **Modal** — parallel research worker execution, sandboxed isolation, timeouts, scale-down
- **Next.js** — intake UI, trace panel, applicability matrix
- **Raindrop** — local trace debugging and replay (not in the customer-critical runtime path)

## Architecture: Artifact-Driven Pipeline

Every stage emits a typed artifact. No free-form model summaries cross stage boundaries.

```
Customer Intake
  -> ScopeAgent         -> ScopePack
  -> OrchestratorAgent  -> ResearchHypothesis[], ResearchTask[]
  -> Modal fan-out      -> EvidenceBundle[]  (one worker per ResearchTask)
  -> VerifierAgent      -> VerificationVerdict (pass/fail/needs_review + RepairTicket[])
  -> [Repair loop]      -> bounded retry, max 2 attempts, terminal = Needs-review
  -> SynthesisAgent     -> Determination[], ApplicabilityMatrix
  -> MemoryWriterAgent  -> GatedMemoryWrite[]  (only verified facts)
```

**Core rule: the orchestrator owns planning; the verifier owns truth.**

Research workers propose conclusions via `EvidenceBundle`. They cannot make final determinations trustworthy — that requires evidence plus verification.

## Typed Artifacts

All artifacts use Pydantic (Python) or Zod (TypeScript). Full schemas are in [`ehs-agent-control-loop-ceo-review.md`](./ehs-agent-control-loop-ceo-review.md).

| Artifact | Producer | Key Fields |
|---|---|---|
| `ScopePack` | ScopeAgent | facility, project_change, missing_facts, assumptions |
| `ResearchHypothesis` | Orchestrator | id, claim, regime, triggering_facts, must_find, acceptance_criteria |
| `ResearchTask` | Orchestrator | task_id, hypothesis_id, allowed_tools, blocked_tools, budget |
| `EvidenceBundle` | ResearchWorker | sources (url, hash, fetched_at, quote), extracted_claims, researcher_conclusion |
| `VerificationVerdict` | VerifierAgent | verdict, checks (currency/authority/grounding/predicate_math), repair_tickets |
| `RepairTicket` | VerifierAgent | failure_type, failed_check, repair_action, max_attempts_remaining |
| `Determination` | SynthesisAgent | applies (yes/no/needs_review), citation, confidence, verified, review_flag |
| `GatedMemoryWrite` | MemoryWriterAgent | memory_type, fact, source_url, content_hash, verifier_verdict |

## Agent Permissions

| Agent | Allowed | Blocked |
|---|---|---|
| ScopeAgent | intake parser, address resolver | final report, memory write |
| OrchestratorAgent | task planner, agent spawn, trace write | direct memory write, final truth decision |
| ResearchWorker | official web fetch, PDF extract, source ranker | final report, durable memory |
| VerifierAgent | source reader, quote checker, predicate evaluator | broad browsing (unless cross-check needed) |
| SynthesisAgent | verified verdicts, matrix/report renderer | unverified source fetch |
| MemoryWriterAgent | verified report, source hashes, run metrics | unverified discoveries |

## Coverage Floor

The orchestrator must always emit a status for every family before spawning specific work:

```json
["air", "stormwater", "hazmat", "waste", "wastewater"]
```

For each family: hypothesis created, missing fact blocks, out-of-scope with reason, or needs discovery. No regulatory family may disappear silently.

## Modal Fan-Out Rules

- One Modal worker per `ResearchTask`
- Worker count = scoped hypotheses + required source-check subtasks (never hardcoded)
- Per-task budget: max 5 sources, 90s runtime, 6 model calls
- Max 5 parallel workers for the hackathon demo slice
- Workers return `EvidenceBundle`s; they do not decide final truth
- Keep intake, orchestration, verification, and synthesis on the app server

## Domain Skills

Skills live in `skills/` and guide source strategy for specific regulatory regimes:

- `skills/air_scaqmd.md`
- `skills/stormwater_igp.md`
- `skills/cupa_hmbp.md`
- `skills/hazardous_waste_ca.md`
- `skills/quote_grounding.md`

Skills are loaded per-task only when needed. They are guidance, not trusted memory.

## Seeded Demo Scenario

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
    "chemicals": [{"name": "flammable solvent", "quantity": 60, "unit": "gallons"}],
    "waste_streams": [{"description": "spent solvent", "kg_per_month": null}],
    "disturbance_acres": 0
  }
}
```

Intentional failure fixture: HMBP worker extracts an overbroad claim ("applies to all storage"); verifier fails grounding; repair worker extracts the threshold (55 gal) and compares to 60 gal; row becomes verified.

## Eval Golden Cases

See [`ehs-agent-test-plan.md`](./ehs-agent-test-plan.md) for the full 10-case suite (EVAL-01 through EVAL-10) and required metrics (≥90% applicability precision, 100% fail-closed, <90s demo latency).

## What Not To Build

- Autonomous filing or portal submission
- Multi-state coverage
- More than 6-8 seeded regulatory programs
- Self-modifying skills during a customer run
- Unbounded recursive agent spawning
- Unverified discovered law written to durable memory

## Build Order

1. Define all Pydantic/Zod artifact schemas
2. Build local deterministic pipeline with cached source fixtures
3. Implement `run_research_task(task)` as a Modal function
4. Add parallel worker launch and result collection
5. Add source fetch, extraction, quote capture, hash, and failure states
6. Add verifier checks (currency, authority, grounding, predicate math)
7. Add bounded repair loop
8. Add trace events for artifact transitions
9. Add matrix UI and evidence drawer
10. Add eval runner against golden cases
