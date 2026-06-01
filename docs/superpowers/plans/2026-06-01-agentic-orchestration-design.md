<!-- /autoplan restore point: ~/.gstack/projects/a1gmm-Autoresearch-Systems-Hackathon-Antler/feat-live-agent-sdk-v1-autoplan-restore-20260601.md -->
# Plan: Agentic orchestration agent

Date: 2026-06-01
Branch: feat/live-agent-sdk-v1 (design doc; implementation targets `main`)
Status: Design APPROVED (/autoplan, 2026-06-01) but **BUILD GATED** (/plan-ceo-review, 2026-06-01): do not start this build until the traction coverage test (see office-hours design doc) shows the current 5-family system is insufficient AND a customer commits. P4 RESOLVED → verifier sole-holder + actively re-derives expected permits from `programRegistry` × scope (the recall floor).
Intent (verbatim): "I would love to work on design how should the orchestration agent do. The orchestration agent when providing hypothesis against users input, it should instruct intake agents to ask as many details as possible for the project scope, then it should reason with itself then spawn off different subagents that we build, all the coverage family should be skill and the verification agent should be able to access the entire lists of different permits with what does it do, no other agent should have the list"

## Build gate (CEO review, 2026-06-01) — READ FIRST

This build is **gated behind traction validation.** Per the office-hours traction design doc (`mac-feat-live-agent-sdk-v1-design-20260601.md`) and this CEO review:

- **Do not start this build yet.** The decisive product question, does PermitPilot's output cover a real ~$10k memo, is answered by running the coverage benchmark on the CURRENT 5-family system. This build delivers zero traction signal.
- **The coverage test is the go/no-go AND the spec.** Build the agentic orchestrator only when BOTH hold: (1) a real memo needs permit families beyond the current 5 (fire-code, CEQA, OSHA PSM, county regimes), proving open-ended discovery is actually necessary, and (2) a customer commits (paid pilot or a hard testimonial).
- **If the 5 families cover the real memo,** this orchestrator is premature. Ship the validated 5-family product, get customers, revisit when volume or a real coverage gap justifies it.
- **If the test reveals a small, specific gap,** prefer the thin-slice response (add the proven-missing families) over the full agentic rebuild until volume justifies it.

The architecture below stays approved and correct. The gate is about WHEN to build, not whether the design is sound.

## What this changes

Today the "orchestrator" is deterministic code (`planResearch`) that iterates a
**hardcoded list of 5 coverage families** and emits fixed hypothesis IDs
([planner.ts:11](../../../src/lib/research/planner.ts)). It can only ever "find" permits
someone pre-listed in code — a project needing fire-code, CEQA, OSHA PSM, or a
county-specific regime gets silent zero coverage. This plan replaces it with a **reasoning
LLM orchestration agent** that:

1. drives the **intake agent** to gather as much project scope detail as possible,
2. **reasons** over the scope to propose the candidate permit set *open-endedly*,
3. **spawns research subagents** (the contextual team) per hypothesis,
4. treats every **coverage family as a modular skill** (read on demand), not a hardcoded enum,
5. and makes the **verifier the sole holder of the master permit list** (what each permit is
   and does), used as the completeness authority — no other agent holds the full list.

## Premises (CONFIRM AT GATE — not auto-decided)

- **P1 — Agentic orchestrator.** The orchestration tier becomes a reasoning LLM agent, replacing the deterministic `planResearch`. (Extends Decision 5 from the prior live-agent plan.)
- **P2 — Coverage families as skills.** Each family becomes a modular `SKILL.md` the orchestrator/researchers load on demand; the family universe is open-ended discovery, not the hardcoded 5-element array.
- **P3 — Deep intake.** The orchestrator instructs the intake agent to gather maximum scope detail before research, minimizing `missing_facts`.
- **P4 — Verifier is the sole permit-list holder.** The canonical list of all permits + what each does lives ONLY with the verifier, which uses it for completeness / silent-drop checking. The orchestrator and researchers do NOT hold the list — they discover/propose; the verifier independently checks coverage against the master list.

## Current state (verified against the code)

- `planResearch` hardcodes `coverageFamilies = ["air","stormwater","hazmat","waste","wastewater"]` ([planner.ts:11](../../../src/lib/research/planner.ts)); deterministic `coverageStatusFor`/`anglesFor`/`hypothesesFor` with fixed hypothesis IDs. The `CoverageFamily` *type* lists 9 (adds `land_use`, `fire_code`, `ceqa`, `osha`) but only 5 are wired.
- `parseScope` is already LLM-driven ([scope.ts](../../../src/lib/research/scope.ts), OpenAI) → `ScopePack` + `missing_facts`.
- Intake agent exists: `app/api/intake/chat/route.ts` (OpenAI, one question at a time, `submit_intake` tool, server-owned prompt).
- The tool catalog **already declares the agentic seams** the hardcoded planner ignores: `map_query_programs` (planner/triage — map jurisdiction→candidate programs), `discover_regime`/`propose_map_entry` (discovery role — novel regimes), `verify_determination_set` (verifier — "check the full candidate set for **silent drops**"). 
- `read_skill` + `src/lib/research/skills/<id>/SKILL.md` (merged via PR #15) is the just-in-time domain-knowledge skill pattern. **Coverage-families-as-skills (P2) extends it directly.**
- Precedent for a scoped, single-purpose role holding its own data: the `sds_reviewer` role + tool set.

## Proposed architecture (rough — review will deepen)

```
intake agent (deep) ── orchestrator instructs: gather max scope detail
        │ ScopePack (+ minimal missing_facts)
        ▼
ORCHESTRATOR AGENT (LLM, reasons with itself)
   - loads relevant coverage-family SKILLS (read_skill) for triggers/thresholds
   - proposes candidate permits/hypotheses OPEN-ENDEDLY (no hardcoded family list)
   - spawns one research subagent per hypothesis
        │ EvidenceBundle[] (grounded: real source + verbatim quote, else needs_review)
        ▼
VERIFIER (sole holder of the MASTER PERMIT LIST)
   - per-claim grounding/currency/predicate checks (existing)
   - verify_determination_set: checks the proposed set against the master list
     for SILENT DROPS — the completeness authority
        ▼
synthesize → applicability matrix
```

The split is generate-then-verify-completeness: the orchestrator **generates** the
candidate set (recall via reasoning + family skills; may be incomplete), and the verifier
**proves coverage** against the authoritative master list (catches what the orchestrator
missed). Centralizing the list in the verifier makes "did we cover everything?" a single,
auditable authority.

## Key design tension (for the review to resolve)

P4 means the orchestrator proposes permits *without* the master list. Open questions:
- **Recall** — how does the orchestrator avoid missing permits if it can't see the full list? (family skills carry per-family triggers; the verifier's silent-drop check is the backstop — but a backstop that only flags after the fact still needs the orchestrator to have proposed *something* in that family.)
- **Grounding** — a proposed permit must resolve to a real regime + fetched primary source, or be flagged `needs_review`, never asserted (no hallucinated permits).
- **What is "the master list"?** A data structure (program registry: permit → what it is, triggers, jurisdiction, authority source) the verifier owns. Today `map_query_programs` + the per-family skills hold fragments; P4 consolidates the authoritative copy in the verifier.

## Open decisions for the review

- D-P4 (information architecture): verifier as *sole* list-holder vs. orchestrator also gets *read-only* recall access. (P4 says sole; the recall tension may argue for shared read.)
- D-FAMILY-SKILL: how a family skill encodes "what permits live in this family" so the orchestrator can propose without the master list.
- D-ORCH-RUNTIME: same OpenAI agentic-loop substrate as the research `worker_core`, or a distinct orchestration loop.

## CEO Review (Phase 1) — Strategy & Scope

Mode: **SELECTIVE EXPANSION** (hold the user's scope; cherry-pick expansions that are in blast radius). Premise gate: all 4 confirmed (verifier sole list-holder).

### What already exists (leverage map)

| Sub-problem | Existing code to reuse |
|---|---|
| Deep intake | `app/api/intake/chat` (OpenAI + `submit_intake`) + `scope.ts` `parseScope` + `ScopePack.missing_facts` |
| Agentic reasoning loop | `modal/worker_core.py` `run_research_agent` (catalog-governed OpenAI tool loop) — same substrate the orchestrator can reuse |
| Families as skills | `read_skill` + `src/lib/research/skills/<id>/SKILL.md` (PR #15) + `skillForHypothesis` |
| Spawn subagents | `toolCatalog` `spawn_subagents`/`wait_for_subagents` (planner) + the research worker |
| Open-ended discovery | `toolCatalog` `discover_regime`/`propose_map_entry` (discovery role) + `map_query_programs` |
| Verifier completeness | `verifier.ts` `verify_determination_set` ("silent drops") |

Takeaway: ~80% of the primitives already exist. The work is **wiring them into an agentic loop + building the master permit registry** — not greenfield.

### Implementation alternatives (0C-bis)

| Approach | What | CC effort | Recall risk | Hallucination risk |
|---|---|---|---|---|
| A. Fully-open LLM discovery | orchestrator free-proposes permits from reasoning + family skills only | low | **HIGH** (no recall floor) | **HIGH** |
| B. Registry + retrieval | orchestrator retrieves candidates from a real program registry (`map_query_programs` over a KB); discovery only for gaps | med (build registry) | low | low (grounded in registry) |
| C. Hybrid (recommended) | B + LLM reasoning to expand/contextualize + `discover_regime` for novel regimes + verifier silent-drop backstop | med-high | **lowest** | low |

Recommendation (P1 completeness): **C**. Critical realization: C needs the master permit registry to EXIST — which is exactly the "master list" P4 puts in the verifier. **The registry IS the master list; the only design question is who reads it.**

### Strategic crux (CEO finding — surfaced at gate)

P4 ("only the verifier has the list") + the compliance recall requirement collide. For a compliance product the fatal error is a **silent false-negative** (missing an applicable permit). Open-ended discovery (A) has no recall floor. The resolution: the verifier's `verify_determination_set` must do a **real completeness diff** — proposed permits vs the master registry, flagging gaps as `needs_review`. Then the orchestrator's recall need not be perfect because **the verifier is the recall backstop**. This is the load-bearing mechanism; it must be BUILT, not assumed. → The Eng phase must lock down exactly how the verifier diffs against the list, and whether a wholly-missed *family* (not just a missed permit within a touched family) is still caught.

### Scope decisions

- **IN** (blast radius + completeness): agentic orchestrator loop; families-as-skills (extend `read_skill`); the **master permit registry** (the "list"); verifier completeness diff against it; deep-intake driving.
- **DEFERRED → TODOS**: agentic-trace UI; multi-jurisdiction registry beyond SoCal; human-approval workflow for discovered novel regimes (`propose_map_entry` already stages this).
- **REJECTED**: fully-open discovery with no registry (A) — fails the compliance error-direction test (P4 + recall).

### Dream-state delta

CURRENT: hardcoded 5 families, can't find anything else. THIS PLAN: open-ended, registry-grounded discovery across any number of families, verifier-enforced completeness. 12-MONTH IDEAL: registry self-updates (`freshness_sweep`), discovery proposes novel regimes for human approval, coverage provably complete per jurisdiction.

### Decision Audit Trail (CEO)

| # | Phase | Decision | Class | Principle | Rationale |
|---|---|---|---|---|---|
| 1 | CEO | Approach C (hybrid registry + reasoning + discovery) | Taste | P1 | A fails compliance recall; C grounds proposals + keeps open discovery |
| 2 | CEO | "Master list" = a real program registry artifact (the verifier's) | Mechanical | P2 | It's the core of P4; in blast radius |
| 3 | CEO | Deep-intake driving in scope | Mechanical | P2 | Small extension of the intake completeness gate |
| 4 | CEO | Multi-jurisdiction registry deferred | Mechanical | P3 | Out of blast radius; SoCal-first |

### CEO dual voice

**Codex:** `[codex-unavailable]` (gpt-5.5/auth failure — single-voice run).

**CLAUDE SUBAGENT (CEO — strategic independence):**
- **[CRITICAL] The master permit registry does not exist in code.** Grep for any registry/master-list/programRegistry returns zero; only the 5 skill dirs + the 9 `SOURCE_POINTERS` exist. P4 pivots on an unbuilt artifact — until it exists, P4 is a naming convention, not an architecture. **Build the registry first; it's the actual moat.**
- **[CRITICAL] Error-direction is inverted.** For compliance, a silent false-negative (missed applicable permit → client fined/shut down) is catastrophic; over-proposing is merely annoying. Open LLM recall + a verifier that only checks what was proposed *maximizes* silent-false-negative exposure. Safe posture: **recall-maximizing — enumerate the registry against scope, propose a superset defaulting to `needs_review`, verifier/human prunes.**
- **[HIGH] P4 sole-holder is clever-but-fragile.** A verifier can only catch a silent drop for a *never-proposed* family if the verifier itself enumerates the master list — which means the verifier is doing discovery, collapsing the generate/verify split. Recommends the orchestrator get **read-only recall access** to the registry; verifier stays the independent completeness auditor, not the only one who can see what exists.
- **[HIGH] Reframe:** the 10x win is the curated program registry (the long tail of regimes), not the information architecture. The orchestrator is plumbing.
- **[MEDIUM] Dismissed alternatives:** data-driven trigger config (expand families without code); deterministic registry sweep for known regimes + `discover_regime`/`propose_map_entry` (which already exist) flagged `needs_review` only for novel ones.

**CEO CONSENSUS TABLE:**
```
  Dimension                              Me      Subagent  Consensus
  ───────────────────────────────────── ─────── ───────── ──────────
  1. Right problem (recall is the game)? yes     yes       CONFIRMED
  2. Registry must exist / be built 1st? yes     yes       CONFIRMED (elevate to headline)
  3. P4 sole-holder as stated is sound?  no       no        CONFIRMED-AGAINST → USER CHALLENGE
  4. Error-direction (over-propose)?     yes     yes       CONFIRMED (recall-max, default needs_review)
  5. Open discovery w/o registry OK?     no       no        CONFIRMED-AGAINST (reject approach A)
```
Codex missing = N/A. Both available voices agree on all five.

### → USER CHALLENGE (P4) — flagged for the final gate, NOT auto-decided

- **You said:** "the verification agent should be able to access the entire list of different permits... no other agent should have the list" (confirmed at the premise gate as P4, sole-holder).
- **Both voices recommend:** the orchestrator gets **read-only** access to the registry for recall; the verifier remains the *authoritative owner + completeness auditor* but isn't the *only reader*.
- **Why:** with the orchestrator blind to the list, recall depends entirely on LLM reasoning + family skills; the verifier's silent-drop check can only flag a missed permit in a family the orchestrator *already touched* — a wholly-missed family is invisible. In a compliance product, that's the catastrophic error.
- **What we might be missing:** you may want the strict boundary for auditability/separation-of-duties reasons (the verifier as an independent check that can't be gamed by the generator), or you may plan the family skills to carry enough per-family permit enumeration that orchestrator recall is adequate without the full list.
- **If we're wrong (we keep sole-holder and it was a mistake), the cost is:** silent false-negatives — applicable permits never proposed, never flagged, shipped as "complete."

### Headline reframe (from this phase)

The plan's center of gravity moves: **the master permit registry is the headline deliverable** (it doesn't exist and everything depends on it). The agentic orchestrator + families-as-skills are the consumers of it. P4 (who reads it) is a real decision, surfaced as the User Challenge above.

## Eng Review (Phase 3) — Architecture & Tests

(Design + DX phases skipped: no new UI screens; the "skills" are internal domain modules, not a dev-facing SDK. Agent-tool ergonomics folded in below.)

### Eng dual voice

**Codex:** `[codex-unavailable]`.

**CLAUDE SUBAGENT (eng — independent):**
- **[CRITICAL] The load-bearing seams don't exist.** `verify_determination_set`, `map_query_programs`, the master list, and the agentic orchestrator are catalog/prose declarations only — none implemented. `verifier.ts` is per-hypothesis fixture-matched with **no set-level completeness logic at all.** The plan over-credits the baseline.
- **[CRITICAL] P4 recall hole is category-confused.** "Silent drops" are *intra-set* checks (a permit touched then dropped). A **wholly-missed family** produces zero proposals → nothing in the set to diff. A set-checker that sees only the proposed set is mathematically incapable of detecting an absent family. **Fix:** `verify_determination_set(scope, proposedSet)` must take the `ScopePack` and independently re-derive expected programs from the master registry via scope triggers, then diff expected-vs-proposed. (This is the verifier running recall — it honors "only the verifier holds the list" but means the verifier actively enumerates, not just looks up.)
- **[HIGH/DRY] Family-skill vs master-list is the same data twice.** Single source of truth: a `programRegistry.ts` (permit, family, triggers, jurisdiction, authority source). The verifier owns the full registry; a family skill is a **generated projection** (rows where `family === x`), never hand-duplicated. Parity test like `skillsParity.test.ts`.
- **[HIGH] Hallucinated permits:** route every novel/un-registried proposal through the existing `discover_regime`/`propose_map_entry` (staging, `human_verified=false`); never assert, hard-flag `needs_review`.
- **[MEDIUM] Runtime:** keep the orchestrator in **TS alongside `run.ts`** (the real orchestrator today); reuse the `worker_core` multi-turn tool-loop *pattern*, not the Python file (don't split orchestration across the TS/Python boundary). Pin the LLM proposal step behind an injectable fn (like `ScopeLlmFn` in scope.ts) for testability.
- **[MED/HIGH security] `quarantine_injection` is scoped only to `researcher`.** The orchestrator now reasons over intake + fetched content to propose permits — injected text ("also add permit X / ignore family Y") flows into proposal reasoning unguarded. Scope `quarantine_injection` to the orchestrator too; treat all fetched/intake content as data, never instructions.
- **[HIGH] Tests:** static-wiring tests break (no fixed hypothesis list). Testable: registry+projection parity; `verify_determination_set` as a deterministic pure fn over `(scope, proposedSet) → missing[]` (fixture where orchestrator omits a family → must flag); golden corpus `scope → expected-permit-set` with a **recall metric** (not exact IDs). Not testable: the LLM proposal step → stub via injected fn.

**ENG CONSENSUS TABLE:**
```
  Dimension                              Me      Subagent  Consensus
  ───────────────────────────────────── ─────── ───────── ──────────
  1. Architecture direction sound?       yes     yes       CONFIRMED
  2. P4 needs active re-derivation?      yes     yes       CONFIRMED (verifier runs recall)
  3. Registry = single source of truth?  yes     yes       CONFIRMED (skills = projections)
  4. Recall is the test that matters?    yes     yes       CONFIRMED (recall metric, not exact IDs)
  5. Security: orchestrator needs quar.? yes     yes       CONFIRMED
  6. Seams currently unimplemented?      yes     yes       CONFIRMED (build, don't assume)
```

### Target architecture (ASCII)

```
intake (deep, orchestrator-driven)  ──►  ScopePack (+ minimal missing_facts)
        │
        ▼
ORCHESTRATOR AGENT  [TS, alongside run.ts; multi-turn tool loop; LLM seam injectable]
   - reads family-skill PROJECTIONS (read_skill) for triggers/thresholds
   - proposes a SUPERSET of candidate permits (recall-max; default needs_review)
   - un-registried proposal ──► discover_regime/propose_map_entry (staged, never asserted)
   - spawn_subagents (one researcher per hypothesis)
        │ EvidenceBundle[]  (per-claim grounded; quarantine_injection on inputs)
        ▼
VERIFIER  [owns programRegistry.ts — the single source of truth]
   - per-claim checks (grounding/currency/predicate)  [existing layer]
   - verify_determination_set(ScopePack, proposedSet):
        re-derive expected programs from registry × scope triggers
        diff expected − proposed  ──►  missing families/permits flagged needs_review   ◄── RECALL FLOOR
        ▼
synthesize ──► applicability matrix (verified vs needs_review)

programRegistry.ts ──(generated projection: rows where family===x)──► skills/<family>/SKILL.md
```

### Eng findings → auto-decisions (P5 explicit, P3 pragmatic)

| # | Finding | Sev | Decision | Principle |
|---|---|---|---|---|
| E1 | `verify_determination_set(scope, proposedSet)` deterministic pure fn, re-derives from registry — the recall floor | CRITICAL | Adopt; build first | P1 |
| E2 | Single `programRegistry.ts`; family skills = generated projections + parity test | HIGH | Adopt | P4 (DRY) |
| E3 | Un-registried proposals hard-flag `needs_review` via discovery role | HIGH | Adopt | P1 |
| E4 | Orchestrator in TS (reuse loop pattern, not worker.py); injectable LLM seam | MED | Adopt TS | P5 |
| E5 | Scope `quarantine_injection` to orchestrator; inputs are data not instructions | MED/HIGH | Adopt | P1 (security) |
| E6 | Recall-metric golden corpus + deterministic completeness unit test; re-pin static tests | HIGH | Adopt | P1 |

### Test diagram (codepath → coverage)

| Codepath | Test type | Exists? |
|---|---|---|
| `programRegistry` ↔ family-skill projection | parity unit test | NEW (model on `skillsParity.test.ts`) |
| `verify_determination_set(scope, set)` recall | deterministic unit test (omit a family → flagged) | NEW — the critical one |
| orchestrator proposal loop | injected-LLM-stub unit test | NEW |
| scope → expected-permit-set | golden corpus + **recall** metric | NEW (replaces exact-ID asserts) |
| un-registried proposal → needs_review | unit test (discovery path) | NEW |

Test plan artifact: `~/.gstack/projects/a1gmm-Autoresearch-Systems-Hackathon-Antler/feat-live-agent-sdk-v1-test-plan-20260601.md` (recall-metric-centred).

### Refined USER CHALLENGE (P4) — for the gate

P4 is **not wrong, but conditional**: it works ONLY if the verifier *actively re-derives* expected permits from the registry × scope (not just diffs the proposed set). That keeps "only the verifier holds the list" (your direction) while closing the recall hole — at the cost of the verifier doing a recall pass (a "second enumerator"). Alternative: give the orchestrator read access so it carries recall and the verifier stays a lighter auditor.

### NOT in scope / What exists

Same as CEO phase. New build: `programRegistry.ts`, `verify_determination_set` impl, the agentic orchestrator (TS), family-skill projection generator + parity test, recall golden corpus. Reuse: `read_skill`/skills, `discover_regime`/`propose_map_entry`, `spawn_subagents`, intake, `scope.ts` LLM-seam pattern.

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 2 | gated | Gate the build behind the traction coverage test (this run) + autoplan CEO phase |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | clean | 6/6 consensus (via /autoplan): registry SoT + active-recall verifier |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | — | skipped (backend) |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | unavailable | codex down on this machine; single-voice runs |

**CEO review (2026-06-01, this run) — mode: scope reduction / gate.** Decision: the agentic-orchestration BUILD is gated behind the traction coverage test (see Build gate, top). The test runs on the current 5-family system, so this build delivers no validation; the test is both go/no-go AND spec. No build starts until a real memo needs families beyond the 5 AND a customer commits. The doc reviewed was the office-hours traction design doc, a strategy doc with no new architecture/error-paths/perf/deploy, so implementation sections 1-11 are N/A; the architecture review lives in the Eng phase below.

**Prior /autoplan review (2026-06-01) — still valid for WHEN this is built:**
- Premise gate 4/4 (P4 sole-holder). USER CHALLENGE (P4) resolved → Option A (verifier sole-holder + actively re-derives).
- CEO 5/5: `programRegistry` does not exist and is the real headline deliverable; error-direction must be recall-maximizing.
- Eng 6/6: P4 sound only with an active-recall `verify_determination_set(scope, proposedSet)`; single `programRegistry.ts` source of truth, family skills as generated projections; `quarantine_injection` scoped to the orchestrator.
- Build order (when the gate clears): programRegistry → verify_determination_set + test → family-skill projection generator + parity test → agentic orchestrator (TS, injectable LLM seam) → recall-metric golden corpus.

- **Deferred → TODOS:** multi-jurisdiction registry; agentic-trace UI; human-approval workflow for novel regimes.
- **UNRESOLVED:** 0.
- **VERDICT:** Design APPROVED, **BUILD GATED.** The next real action is the office-hours assignment (run one real memo through the current system), not this build. Implement only after the coverage test shows more than 5 families are needed AND a customer commits.
