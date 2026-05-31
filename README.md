# PermitPilot — EHS Permit-Navigator

Home repo: https://github.com/a1gmm/Autoresearch-Systems-Hackathon-Antler

PermitPilot is an AI-native **Environmental, Health & Safety (EHS) research swarm**: it
turns a free-text description of a facility or project change into a **defensible
regulatory applicability matrix** — every "this permit applies" row backed by a current,
quoted primary source, and every gap **failing closed** to human review rather than
guessing.

> **Demo target:** Given a Southern California manufacturing change, the agent swarm
> determines the applicable EHS obligations, proves each row with current source
> evidence, and visibly fails closed when evidence is incomplete.

---

## The problem

### 1. The domain problem

Working out which EHS permits apply to a change (a new coating booth, a solvent tank, an
acre of grading) is slow, expert-gated, and high-stakes. The facts live in dozens of
agency rulebooks (SCAQMD, the California Water Boards, CalEPA/CUPA, US EPA), the
thresholds are numeric and exception-riddled, and a wrong "does not apply" is a
compliance liability. The work is fundamentally **research**: find the controlling rule,
prove it is current, compare the project's numbers to the threshold, and cite the exact
clause.

### 2. The architectural problem: the orchestrator hands the team a *different* hypothesis set every run

PermitPilot is a multi-agent pipeline, and its hard part is that **the work is not fixed
in advance.** The orchestration stage reads each project and emits a *project-specific*
set of research hypotheses:

- **`parseScope` is LLM-driven** ([`scope.ts`](src/lib/research/scope.ts)) — it extracts
  structured facts (equipment, chemicals + quantities, waste streams, disturbed acres,
  process discharge, NAICS/SIC) from free text, and records `missing_facts` for anything
  decision-relevant that is absent. It never invents values; with no key or a failed
  extraction it falls back to an `emptyScope` that blocks everything.
- **`planResearch` is fact-gated** ([`planner.ts`](src/lib/research/planner.ts)) — each
  coverage family (air, stormwater, hazmat, waste, wastewater) is marked `active`,
  `out_of_scope`, or `blocked_missing_fact` *from those facts*. Only live families spawn
  regulatory angles, and only angles spawn hypotheses.

So a project with no chemicals produces **no** hazmat hypothesis; a project that adds
equipment produces air hypotheses; a project missing its SIC/NAICS produces a
`blocked_missing_fact` for stormwater. **The hypothesis set — and its size — changes
with the project.**

That dynamism is the design challenge that shapes the whole system:

| Because hypotheses are dynamic… | …the system must |
|---|---|
| There is **no fixed list** of hypothesis IDs | Operate on whatever the orchestrator emitted, keyed by id/family at runtime — never hardcode per-ID logic |
| Downstream once **rubber-stamped** the known demo IDs | Verify with **real grounding** for *any* hypothesis (quote ↔ claim), and synthesize from the researcher's actual conclusion |
| LLM scope extraction is **non-deterministic** | Evaluate with **key-gated, tolerant, dynamism-aware** golden cases, not exact-match snapshots |
| Some facts are **missing** | **Fail closed**: block the family, flag `needs_review`, never guess |

The rest of this document is the structure that makes that work.

---

## Architecture

```
            free-text project change
                      │
        ┌─────────────▼──────────────┐
        │  INTAKE  (OpenAI chat)      │  app/api/intake/chat  — gather facts, one Q at a time
        └─────────────┬──────────────┘
                      │ project_description
        ┌─────────────▼──────────────┐
        │  ORCHESTRATION              │
        │   parseScope   (LLM)        │  scope.ts   free text → ScopePack facts (+ missing_facts)
        │   planResearch (fact-gated) │  planner.ts ScopePack → families → angles → HYPOTHESES
        └─────────────┬──────────────┘
                      │ research_tasks  (one per active hypothesis → a family researcher)
        ┌─────────────▼──────────────┐
        │  RESEARCH AGENT TEAM        │  workers.ts → researchPool → worker_core (agentic loop)
        │   fixture | live (Modal)    │  fetch primary source · prove currency · extract · ground
        └─────────────┬──────────────┘
                      │ EvidenceBundle[]   (the distilled per-hypothesis result)
        ┌─────────────▼──────────────┐
        │  VERIFY (+ repair)          │  verifier.ts  4-level checks · real grounding · repair loop
        └─────────────┬──────────────┘
                      │ verdicts + confidence
        ┌─────────────▼──────────────┐
        │  SYNTHESIZE                 │  synthesis.ts → applicability matrix + determinations
        └─────────────┬──────────────┘
                      ▼
            ResearchRun  (matrix · evidence · verdicts · trace events · report)
                      │
            UI report + trace panel   ·   (durable runs: Modal spawn + Supabase poll)
```

The integration seam between the team and everything downstream is the **`EvidenceBundle`**:
researchers *produce* it; the verifier and synthesizer *consume* it. Swapping a fixture
researcher for a live one is a producer swap behind that contract.

---

## The pipeline, stage by stage

1. **Intake** ([`app/api/intake/chat/route.ts`](app/api/intake/chat/route.ts)) — an OpenAI
   chat assistant gathers facts one question at a time and submits a structured intake.
   The system prompt is server-owned and the route strips any client-supplied
   `system`/`tool` messages (prompt-injection hardening).
2. **Scope** ([`scope.ts`](src/lib/research/scope.ts)) — `parseScope` turns the description
   into a typed `ScopePack` with explicit `missing_facts`. Fail-closed `emptyScope` when
   extraction is unavailable.
3. **Plan** ([`planner.ts`](src/lib/research/planner.ts)) — `planResearch` expands the
   scope into `CoverageFamilyStatus[]` → `RegulatoryAngle[]` → `ResearchHypothesis[]` →
   `ResearchTask[]`. This is the orchestrator deciding *what the team investigates*.
4. **Research team** ([`workers.ts`](src/lib/research/workers.ts),
   [`modal/worker.py`](src/lib/research/modal/worker.py)) — one worker per task.
   A worker is a **catalog-governed agentic loop**: it may fetch allowlisted sources,
   prove currency, extract the triggering clause + verbatim quote, evaluate the predicate,
   and quarantine injection — then returns an `EvidenceBundle`.
5. **Verify (+ repair)** ([`verifier.ts`](src/lib/research/verifier.ts)) — real grounding,
   currency, authority, predicate-math, and cross-source checks. A failed grounding check
   files a **repair ticket** that re-runs the failed step within a bounded budget.
6. **Synthesize** ([`synthesis.ts`](src/lib/research/synthesis.ts)) — assembles the
   applicability matrix from the *researcher's* conclusion + verifier verdict; review-flags
   anything unverified or blocked.
7. **Run assembly** ([`run.ts`](src/lib/research/run.ts)) — orchestrates the above, emits
   `trace_events` for the UI, and wraps the run in Raindrop telemetry.

---

## The hypothesis lifecycle (worked example)

> *"A SoCal manufacturer adds a coating booth and stores 60 gallons of flammable solvent
> with spent-solvent waste."*

```
parseScope  →  equipment:[coating_booth]  chemicals:[solvent 60 gal]  waste:[spent solvent]
            →  missing: facility.naics_or_sic (blocks stormwater)

planResearch →  air        ACTIVE          → A-AIR-EMITTING-EQUIPMENT  → H-AIR-201, H-AIR-VOC
            →  air        ACTIVE          → A-AIR-EXEMPTION-OR-REG     → H-AIR-219, H-AIR-222
            →  hazmat     ACTIVE          → A-HAZMAT-HMBP              → H-HAZMAT-HMBP
            →  waste      ACTIVE          → A-WASTE-GENERATOR-STATUS   → H-WASTE-GENERATOR
            →  stormwater BLOCKED_MISSING → (no SIC/NAICS, no acres)   → needs_review
            →  wastewater BLOCKED_MISSING → (discharge not stated)     → needs_review

each ACTIVE hypothesis → ResearchTask {assigned_agent: "<family>_researcher", budget, tools}
                       → dispatched to the research agent team
```

A different project yields a different set: drop the chemicals and **hazmat** goes
`out_of_scope` (no hypothesis at all); add no equipment and **air** goes `out_of_scope`.
Hypothesis and angle **IDs are stable labels** (e.g. `H-HAZMAT-HMBP`), but *which* ones
appear, and how many, is computed per run.

---

## Core data contracts

Defined in [`types.ts`](src/lib/research/types.ts); these are the artifacts that cross
agent boundaries.

| Type | Role |
|---|---|
| `ScopePack` | Structured project facts + `missing_facts` + assumptions (output of scope) |
| `CoverageFamilyStatus` | Per-family `active` / `out_of_scope` / `blocked_missing_fact` + reasons |
| `RegulatoryAngle` | A specific regulatory question within a family |
| `ResearchHypothesis` | One testable claim (`question`, `claim_to_test`, `success_criteria`, `family`) |
| `ResearchTask` | A hypothesis packaged for a worker: `allowed_tools`, `blocked_tools`, `budget` |
| `EvidenceBundle` | A worker's distilled result: `sources` (url/quote/hash/authority), `extracted_claims`, `researcher_conclusion`, `uncertainties` |
| `VerificationVerdict` | Per-hypothesis `pass` / `fail` / `needs_review` + named checks + repair tickets |
| `Determination` | A synthesized matrix row: requirement, `applies`, `verified`, `review_flag` |
| `ResearchRun` | The whole run: scope, graph, evidence, verdicts, determinations, trace events, report |

---

## The agent harness & tool catalog

Agents do not get arbitrary capabilities — every tool is declared once and **scoped to a
role**.

- [`toolCatalog.ts`](src/lib/research/toolCatalog.ts) — the tool → role/category/write-target
  contract (`fetch_source`, `extract_threshold`, `verify_determination`, …). Read-only
  researcher tools, write-bearing synthesis/verifier tools, harness-control tools.
- [`skillRegistry.ts`](src/lib/research/skillRegistry.ts) — the inverse role → capability
  view (a "skill" = trigger + allowed toolset + done condition), kept in sync with the
  catalog by a validator.
- `harness.ts` — runtime enforcement: a `HarnessContext` records tool calls and throws
  `HarnessToolScopeError` if an agent reaches for an out-of-role tool.

Agent roles: `intake`, `planner`, `triage`, `researcher`, `verifier`, `synthesizer`,
`sds_reviewer`, `discovery`, `system`.

---

## Research workers & execution modes

A `RESEARCH_MODE` switch selects how the team runs:

- **fixture** (default; tests/CI/dev) — deterministic canned evidence, no network, no API
  cost. The reproducible demo/eval path.
- **live** — a real **agentic worker** ([`modal/worker.py`](src/lib/research/modal/worker.py)):
  a pure, injectable loop driven by `llm_fn` / `fetch_fn` / `extract_fn`, governed by the
  task's tool catalog and budget (`max_sources`, `max_runtime_seconds`, `max_model_calls`).
  It runs through the **Modal** CLI bridge today (fan-out, isolation, timeouts), with a
  fixture/degraded-trace fallback; the durable HTTP endpoint is a follow-up branch.

The worker is intentionally **pure + injectable** so it can be unit-tested
(`worker_core_test.py`) without Modal or a live model.

---

## EHS skills library (`read_skill`) — just-in-time domain knowledge

So that live researchers ground their search in real EHS rule knowledge instead of a bulky
system prompt, the team can pull a domain **skill** on demand:

- Skill files at `src/lib/research/skills/<id>/SKILL.md` — one per coverage family
  (`scaqmd-air`, `ca-stormwater`, `ca-hmbp`, `hazwaste-generator`,
  `industrial-pretreatment`), each with triggers, a thresholds table, exemptions, and
  authoritative source URLs.
- The `read_skill` tool (a researcher-scoped `knowledge_base_read` entry) + a
  `SKILL_FOR_HYPOTHESIS` map surface the right skill in each task's context.
- **Guardrail — skills orient, fetched sources ground:** a skill is the *map* (what to look
  for, expected ranges); the fetched primary regulation + verbatim quote is the *proof*.
  A `SKILL.md` is never citable evidence, and a host allowlist (`sourceAllowlist.ts`)
  constrains what may be fetched.

> Status: this layer is new and lands on a feature branch; see *Status & branches* below.

---

## Verification & confidence

The verifier is a **mechanical backstop** — deliberately *not* an LLM persona — so the
research/synthesis agents cannot reason their way past it.

- **Four levels:** claim (grounding/currency/authority/predicate-math), self-consistency,
  determination-set coverage, and process-trace integrity.
- **Real grounding for the generic path:** every bundle's quote must actually support its
  claim; no rubber-stamping by authority rank. A failed grounding check → a **repair
  ticket** → a bounded re-run.
- **Confidence is computed, not asserted** ([`confidence.ts`](src/lib/research/confidence.ts)):
  `computeConfidence` *caps* (a failed check ceilings confidence; passing others can't buy
  it back) and scales by self-consistency. Low/blocked/exception cases carry a review flag.

---

## Durable runtime (long live runs)

A real multi-agent web run can exceed the Next/Vercel serverless window, so live runs use a
durable path: `POST /api/research/run` **spawns** a Modal job and returns a `run_id`; the
job writes incremental state to a **Supabase** research-run store (injectable client seam);
`GET /api/research/run/:id` polls status + partial artifacts for the UI.

> Status: durable runtime lives on `feat/durable-runtime`; the synchronous in-process path
> is the default elsewhere.

---

## Repository layout

```
app/
  api/intake/chat/        OpenAI intake assistant (server-owned prompt)
  api/research/run/       run endpoint (sync; durable spawn on feat/durable-runtime)
  components/             report UI, trace panel, applicability matrix
src/lib/research/
  scope.ts                LLM parseScope → ScopePack
  planner.ts              fact-gated plan → families → angles → hypotheses → tasks
  workers.ts              research pool dispatch (fixture | live)
  modal/worker.py         pure agentic research loop + Modal app wrapper
  verifier.ts             4-level verification + repair
  confidence.ts           computeConfidence (cap-don't-average + self-consistency)
  synthesis.ts            applicability matrix + determinations
  run.ts                  orchestrates the pipeline + trace + telemetry
  toolCatalog.ts          tool → role/category/write contract
  skillRegistry.ts        role → capability view (+ validator)
  skills/<id>/SKILL.md    EHS domain knowledge (read_skill)
  types.ts                shared data contracts
src/lib/intake/           intake prompt + completeness gating
src/evals/golden.ts       failure-driven golden eval cases
```

---

## Running locally

```bash
npm install
npm run dev          # Next dev server
npm run test         # vitest (runs in fixture mode — deterministic)
npm run typecheck    # tsc --noEmit
npm run eval         # golden cases (src/evals/golden.ts)
```

Environment:

- `OPENAI_API_KEY` — required for live intake + LLM `parseScope` (omit → fail-closed
  `emptyScope`).
- `OPENAI_INTAKE_MODEL` — optional, defaults to `gpt-4o-mini`.
- `RESEARCH_MODE` — `fixture` (default) or live; live also needs the Modal endpoint + token.

---

## Status & branches

This is hackathon-stage and developed across several feature branches; much of the live
pipeline is merged to `origin/main` (LLM scope, fact-gated planner, real-grounding
verifier, the agentic `worker_core`, HTTP Modal transport). Notable in-flight branches:

- `feat/durable-runtime` — Supabase store + Modal spawn + poll / `GET /:id`.
- `feat/dynamic-planner` / `feat/real-modal-research` — LLM `parseScope` + dynamic planner.
- `agentic-harness` / `feat/computed-confidence` — harness, skill registry, `computeConfidence`.
- EHS skills library + `read_skill` (above) — newest layer, not yet merged.

Confirm the intended base branch before building on top of this tree.

---

## Further reading

1. [Team Share Packet](./TEAM_SHARE_PACKET.md)
2. [Two-Person Build Split](./TWO_PERSON_BUILD_SPLIT.md)
3. [Hackathon Demo Design](./HACKATHON_DEMO_DESIGN.md)
4. [Tool Integration Plan](./TOOL_INTEGRATION_PLAN.md)
5. [Product and Build Plan](./ehs-permit-agent-autoplan-review.md)
6. [Agent Control Loop Contract](./ehs-agent-control-loop-ceo-review.md)
7. [Test and Eval Plan](./ehs-agent-test-plan.md)
8. [Harness vs Tool Catalog](./docs/HARNESS_V_TOOL_CATALOG.md)

## Repository hygiene

- Never commit sponsor credit codes, private API keys, `.env` files, source-cache
  credentials, or customer data.
- Keep demo fixtures small, reproducible, and safe to run without live network access.
- Treat final determinations as **human-review research support — not legal advice or
  autonomous filing.**
