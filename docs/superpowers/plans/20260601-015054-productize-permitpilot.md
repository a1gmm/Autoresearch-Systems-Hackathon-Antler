<!-- /autoplan restore point: /Users/mac/.gstack/projects/a1gmm-Autoresearch-Systems-Hackathon-Antler/feat-live-agent-sdk-v1-autoplan-restore-20260601-015054.md -->
# Productize PermitPilot — five directions

**Date:** 2026-06-01
**Branch:** feat/live-agent-sdk-v1 → base `main`
**Source:** user-supplied rough plan to /autoplan

## Goal (as stated)

Turn the PermitPilot hackathon prototype into a product by pulling the best ideas from two
reference systems (CrossBeam, Permit_-overview) while keeping PermitPilot's core differentiator.

## The five directions

1. **Productize long-running runs like CrossBeam** — persistent orchestrator, durable job state,
   realtime progress, artifact storage.
2. **Expand skills from orientation files into a visible domain library** — reference documents,
   decision trees, test assets.
3. **Make source retrieval fully real** — allowlisted fetch, currency proof, quote-span grounding,
   process-trace verification.
4. **Borrow Permit_-overview's fast UX** — instant demo replay, broad agency/city coverage, clear
   filing sequence / cost / timeline outputs.
5. **Keep PermitPilot's core edge** — typed research graph + verifier-owned truth. The strongest
   thing in the repo; do not dilute it.

## Repo reality (as of base `main`, checked at intake)

- **Durable runtime ALREADY EXISTS (approved + partly built):** `durable/durableRun.ts`,
  `store/supabaseStore.ts`, `useDurableRun.ts`, `supabase/migrations/0001_research_runtime.sql`,
  design doc `2026-05-31-durable-runtime-supabase-design.md`. Opt-in `RESEARCH_RUNTIME=durable`;
  Modal owns durability, Node finalizes on poll, Supabase Realtime pushes progress.
- **Source retrieval partly real:** `modal/worker.py`, `modal/researchPool.ts`, real-modal design
  docs. OpenAI reasoning worker on Modal.
- **UI replay partly exists:** `ReplayControls.tsx`, `useReplay.ts`, `scenarios.ts`.
- **Skills:** 5 orientation `SKILL.md` files (`scaqmd-air`, `ca-stormwater`, `ca-hmbp`,
  `hazwaste-generator`, `industrial-pretreatment`).
- **Core edge intact:** typed `planResearch` graph + mechanical `verifier.ts`.

This plan is a review of whether/how to pursue the five directions given that reality.

---

# Phase 1: CEO Review (Strategy & Scope)

**Mode:** SELECTIVE EXPANSION. **Dual voices:** Claude subagent ran; Codex `[codex-unavailable: CLI 0.118.0 default model gpt-5.5 needs newer CLI; ChatGPT account rejects gpt-5/gpt-5-codex]`. CEO phase is `[subagent-only]`.

## 0A — Premise challenge

The plan rests on premises that the review found to be **false or unproven**:

| # | Stated premise | Verdict |
|---|---|---|
| P1 | "Verifier-owned truth is the strongest thing in the repo; keep it" | **FALSE today.** `verifier.ts` (both branch=185L and origin/main=225L) is hardcoded per-hypothesis-ID with `pass:true` constants (lines 12/41/81) and a generic path that passes everything (107-110). The HMBP "fail" triggers on fixture hash `sha256:demo-hmbp-bad`. It is a scripted demo, not a verifier. The moat does not exist yet. |
| P2 | "Productize + borrow competitor features is the right next move" | **UNPROVEN.** Zero users, untested value hypothesis. Pre-PMF surface-area expansion. |
| P3 | "Direction #1 (durable runtime) is work to do" | **FALSE.** Already merged to main (durableRun.ts, supabaseStore.ts, useDurableRun.ts, migration, approved design doc). |
| P4 | "Broad agency/city coverage + cost/timeline/filing outputs strengthen the product" | **CONTRADICTS the trust thesis.** Cost/timeline/filing are unquotable estimates; rendering them beside fail-closed verified rows dilutes the only moat. |

## 0B — What already exists (DRY map)

| Direction | Existing on main | Verdict |
|---|---|---|
| #1 durable runtime | `durable/durableRun.ts`, `store/supabaseStore.ts`, `useDurableRun.ts`, `supabase/migrations/0001_research_runtime.sql`, approved design doc | **Already built — strike as build item** |
| #3 source fetch (plumbing) | `modal/worker.py`, `modal/researchPool.ts`, real-modal design docs | Fetch partly done; **verification half (currency proof, quote-span grounding) is net-new and critical** |
| #4 replay UX | `ReplayControls.tsx`, `useReplay.ts`, `scenarios.ts` | Replay already built; broad coverage + cost/timeline are net-new and **trust-diluting** |
| #2 skills | 5 orientation `SKILL.md` | Expansion additive but must be scoped to depth, not breadth |
| #5 verifier edge | `verifier.ts` (hardcoded) | **Must be BUILT before it can be "kept"** |

## CEO DUAL VOICES — CONSENSUS TABLE

```
  Dimension                            Claude   Codex   Consensus
  ──────────────────────────────────── ──────── ─────── ──────────
  1. Premises valid?                   NO       N/A     NO (subagent-only)
  2. Right problem to solve?           NO       N/A     NO (subagent-only)
  3. Scope calibration correct?        NO       N/A     NO (subagent-only)
  4. Alternatives explored?            NO       N/A     NO (subagent-only)
  5. Competitive risks covered?        PARTIAL  N/A     PARTIAL (subagent-only)
  6. 6-month trajectory sound?         NO       N/A     NO (subagent-only)
```
Codex unavailable (model/CLI mismatch) → single-critical findings flagged regardless.

## Findings (severity-ordered)

1. **CRITICAL — verifier "owns truth" is not true yet.** Hardcoded per-ID `pass:true` + substring grounding on main. Invalidates Direction #5's premise. Fix: ID-agnostic generic path, claim↔quote entailment grounding, adversarial verifier eval with catch-rate. *This is the product.*
2. **CRITICAL — wrong problem framing.** Pre-PMF surface-area expansion around an unproven core. Fix: reframe to one falsifiable trust claim (one family, one jurisdiction, EHS-pro-trusted + verifier catches planted errors).
3. **HIGH — Direction #1 is DRY waste.** Already built. Fix: strike; rebase onto main.
4. **CRITICAL — Direction #4 broad coverage is the 6-month regret.** Breadth over an untrusted base; one wrong "does not apply" = liability. Fix: narrow + deep.
5. **HIGH — Direction #4 cost/timeline/filing CONTRADICTS #5.** Unquotable estimates dilute the verified brand. Fix: cut now; if ever added, hard-firewall as "estimate, not verified."
6. **HIGH — competitive framing backwards.** Copying CrossBeam's productization runs toward their strength. Fix: compete on provable fail-closed determinations a single-agent system structurally can't do.
7. **MEDIUM — Direction #2 mis-scoped as breadth.** Fix: scope skills expansion to the one family being proven; promote "test assets" (feeds verifier eval).
8. **HIGH — Direction #3 mis-prioritized.** Its verification half is the moat-maker but listed 3rd under done work. Fix: promote to first.

## NOT in scope (deferred / cut)

- Direction #1 durable runtime build (done) → rebase instead.
- Direction #4 broad agency/city coverage → defer post-trust.
- Direction #4 cost/timeline/filing outputs → cut (trust-diluting).
- CrossBeam productization copying → cut.

## Sequencing verdict

1. Rebase onto origin/main (branch is ~50 behind).
2. Make verifier real + adversarial eval (Findings 1, 8) = Directions #3+#5 done properly.
3. Deepen skills + test assets for ONE family (Finding 7).
4. Put one real case in front of one EHS professional; measure trust (Finding 2).
5. Cut: #1 build, #4 both halves, CrossBeam copying.

---

# Phase 3: Eng Review (reframed plan: build the moat)

**Dual voices:** Claude subagent ran (read verifier.ts/confidence.ts/types.ts/synthesis.ts/workers.ts/worker.py/sources.ts/golden.ts). Codex `[codex-unavailable]`. Eng phase `[subagent-only]`.

## ENG DUAL VOICES — CONSENSUS TABLE
```
  Dimension                            Claude   Codex   Consensus
  ──────────────────────────────────── ──────── ─────── ──────────
  1. Architecture sound?               REWRITE  N/A     verifier is a rewrite, not a tighten
  2. Test coverage sufficient?         NO       N/A     new adversarial suite required
  3. Performance risks addressed?      OK       N/A     mechanical checks are cheap
  4. Security/trust threats covered?   PARTIAL  N/A     LLM-in-verifier would break the moat
  5. Error paths handled?              GAP      N/A     contract gaps block grounding+currency
  6. Deployment risk manageable?       MEDIUM   N/A     rebase-first to land contracts cleanly
```

## Architecture (Section 1)
The verifier is NOT tightenable — it's 100% per-ID `if (hypothesis_id===...)` blocks with `pass:true` constants (verifier.ts:12/41/81) + a generic fallback that passes everything (106-118). **Replace with an ID-agnostic pipeline** of pure checks: `checkCurrency, checkAuthority, checkGrounding, checkPredicateMath`, run over `bundle.sources[0]` + `extracted_claims`, never branching on `hypothesis_id`. Predicate threshold+operator+value must travel in the data (extend `extracted_claims` or resolve via `required_facts`), not in code.

```
verifyEvidence(scope, bundle)
  source? no -> needs_review
  checkCurrency  -> null date -> fail(cap .30) | stale -> fail | current -> pass
  checkAuthority -> rank<=2 pass | >=3 fail(cap .50)
  checkGrounding -> quote not verbatim span of source_text -> fail (MISQUOTE)
                 -> claim asserts number/scope quote lacks -> fail (MISMATCH)
                 -> supports -> pass
  checkPredicateMath (data-driven) -> value>=threshold pass | < needs_review | missing needs_review
  UNKNOWN id + good evidence -> runs all 4, no auto-pass, no throw  [no-hardcoding guard]
  grounding fail -> files repair ticket (GENERIC, not HMBP-only)
```

## CRITICAL findings
1. **Verifier is a rewrite (not a fix).** No generic engine exists to harden. Scope accordingly.
2. **CONTRACT GAP — source text not in EvidenceBundle.** Source carries only `quote` (verified: types.ts source has no full-text field). The headline "catch misquotes" check needs the fetched source text to span-match against. worker.py HAS `source_text` but drops it. **Unbuildable until `source_text` is added to the bundle source contract + populated in both workers + fixtures.** Sequence FIRST.
3. **CONTRACT GAP — currency has no data.** All 9 fixtures `effective_date: null` (verified). Currency proof is fiction today. Define semantics: null -> fail-closed needs_review (cap .30); add real dates to demo-critical fixtures + STALE_AFTER_DAYS + injectable `now` (keep verifier deterministic).
4. **BLAST RADIUS — ~7 generic-path rows flip verified->needs_review** when real grounding lands (their fixture quotes are orienting prose, not numeric triggers). Correct + fail-closed, but a visible demo change. Decide per-row: accept needs_review, or upgrade fixture quote to a real trigger. Don't discover at demo time.

## HIGH/MEDIUM
5. **Keep grounding MECHANICAL — no LLM judge.** README hard-promises verifier is "not an LLM persona" so agents can't reason past it. An LLM judge breaks determinism + the moat + reproducible catch-rate. Mechanical = (a) verbatim-span match, (b) regex numeric-threshold + scope-word contradiction guard. If entailment truly needs an LLM, place it in the WORKER (proposes) and let the mechanical verifier spot-check (disposes).
6. **Eval harness is separate from golden.ts.** golden.ts is end-to-end (runResearch). Build `verifierAdversarial.test.ts` (calls verifyEvidence directly) + reportable `src/evals/verifierEval.ts` printing per-category catch-rate, CI-gated at 100%.
7. **golden.ts `complex-facility` breaks** unless "grounding fail -> repair ticket" stays wired in the generic path (repairs come only from the HMBP branch today).
8. **process-trace / self-consistency** declared (confidence.ts FAIL_CAP.cross_source) but unimplemented + verifier never receives trace_events. Either implement (cheap in fixture mode: N re-runs) or cut from the "four levels" moat claim. Don't claim it unbuilt.
9. **Rebase first.** main has the SAME hardcoded verifier (no logic conflict), but findings 2/3 mutate shared contracts (types.ts, workers, sources, worker.py) that main may have churned. Land contract additions on fresh main, then build. Also clean the `* 2.tsx` merge-debris first.

## NOT in scope (eng)
- LLM-as-judge inside the verifier (breaks the moat).
- process-trace verification unless explicitly implemented (else cut the claim).

Test plan artifact: ~/.gstack/projects/<slug>/feat-live-agent-sdk-v1-test-plan-<dt>.md

---

## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale |
|---|-------|----------|----------------|-----------|-----------|
| 1 | CEO | Strike Direction #1 (durable runtime) as build item | Mechanical | P4 DRY | Already merged to main |
| 2 | CEO | Promote Direction #3 verification-half + #5 to priority 1 | Taste | P1 completeness | The only moat-making work |
| 3 | CEO | Cut Direction #4 cost/timeline/filing outputs | Taste | P5 explicit | Unquotable estimates dilute verified brand |
| 4 | CEO | Defer Direction #4 broad agency/city coverage | Taste | P1+P2 | Breadth over untrusted base = 6-mo regret |
| 5 | CEO | Narrow Direction #2 skills to depth-in-one-family | Mechanical | P1 | Skills orient, don't ground (README) |
| 6 | Eng | Verifier = full rewrite to ID-agnostic pipeline | Mechanical | P5 explicit | No generic engine exists to tighten |
| 7 | Eng | Add source_text to EvidenceBundle (contract) FIRST | Mechanical | P2 boil-lake | Misquote grounding unbuildable without it |
| 8 | Eng | Currency null -> fail-closed needs_review | Mechanical | P1 | Fail-closed per README; no date = no proof |
| 9 | Eng | Keep grounding mechanical, NO LLM judge | Taste | P5 explicit | LLM judge breaks determinism + the moat |
| 10 | Eng | Separate adversarial eval from golden.ts | Mechanical | P5 | Unit-level catch-rate vs e2e |
| 11 | Eng | Rebase onto main before contract changes | Mechanical | P3 pragmatic | Avoid late conflict in high-churn files |

## Cross-phase themes
**Theme: the verifier moat is asserted, not built** — flagged independently in CEO (Finding 1, premise P1) AND Eng (Findings 1-3). High-confidence signal: this is the keystone of the whole plan and the single thing to fix first.
**Theme: fail-closed honesty vs demo polish** — CEO Finding 5 (cut unverifiable cost/timeline) and Eng Finding 4 (~7 rows flip to needs_review) both say: real verification makes the demo LOOK worse but BE trustworthy. That tradeoff is the product.

---

## Scope boundary vs the agentic-orchestration plan (2026-06-01)

This worktree (`feat/real-verifier-moat`) builds the **per-claim verification floor**:
verbatim-span grounding + currency + adversarial catch-rate eval. APPROVED, ungated.

The separate `2026-06-01-agentic-orchestration-design.md` builds the **set-completeness
floor** (`programRegistry` + `verify_determination_set` re-derivation + agentic
orchestrator). It is **APPROVED but BUILD-GATED** — do not start until the office-hours
traction test shows >5 families are needed AND a customer commits.

Order: per-claim floor (this) is a prerequisite for set-completeness (that). Build this
now; the gated plan layers on top later when its gate clears. Do NOT build programRegistry
or verify_determination_set in this worktree.

---

## UPDATE — aligned with feat/program-registry (orchestrator work already started)

The orchestration/registry build was started on `feat/program-registry` (3 commits: `programRegistry.ts` single-source-of-truth, `completeness.ts` recall floor / `verifyDeterminationSet`, parity test). The moat worktree is **rebased onto it** — both floors now compose in one tree, toward one goal: a verifier trustworthy on BOTH axes.

| Floor | Question | Owner | Status |
|---|---|---|---|
| **Recall** (set-completeness) | Did we miss an applicable permit/family? | `completeness.ts` + `programRegistry.ts` | DONE on feat/program-registry |
| **Grounding** (per-claim) | Is each proposed permit backed by a quote that supports it? | `verifier.ts` (still 6 hardcoded pass:true branches) | THIS WORKTREE's job |

No file overlap between the two (verified) — clean compose. `feat/real-verifier-moat` now sits on top of `feat/program-registry`; baseline 201 tests green. The moat work (verbatim-span grounding + currency + adversarial eval) makes the per-claim layer real so the recall floor's proposals are also individually trustworthy.
