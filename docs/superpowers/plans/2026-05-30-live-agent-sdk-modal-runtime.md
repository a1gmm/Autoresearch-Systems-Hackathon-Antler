# Plan: Live Agent SDK workers + durable Modal runtime

Date: 2026-05-30
Branch: codex/review-pr-5-vision-gaps
Status: APPROVED (gate cleared 2026-05-30; refined 2026-05-31) — staged v1, in-process SDK, modal.Dict, agentic orchestrator + skills library in v1

Approved shape (final gate):
- **D1 scope → Staged.** v1 = de-risk + a safe live happy-path (generalize the verifier safety hole + consume side, spike the runtime, ship an in-process live worker behind the mode flag, harden injection/budget). v2 = durable Modal runtime + the UI streaming rewrite + record/replay.
- **D2 runtime → In-process for v1.** SDK `query()` runs in the orchestrating/Modal *function* process, not a per-task Modal Sandbox. Per-task sandbox isolation is a v2 follow-up, gated on a spike proving the CLI binary runs in-image.
- **D3 store → modal.Dict for v1.** Ships with the Modal app; migrate to Supabase Postgres when run history / multi-user / Realtime push is a real need.

Post-gate refinements (2026-05-31):
- **D-CONTEXT-ENG → personaless subagents.** System prompts only at the intake + orchestration tiers; researchers are a context-engineered team (Decision 2).
- **D5 → agentic orchestrator in v1.** The orchestration tier is a live LLM agent (decompose + curate + synthesize); the verifier stays a mechanical backstop (Decision 5).
- **Sub-project A → folded into v1.** EHS skills library + `read_skill` just-in-time tool (Sub-project A section).
Intent (verbatim): "swap fixtures for real Agent SDK workers + give it durable runtime with modal"
Premise (RESOLVED at gate): **Full production swap** — all hypotheses researched live via Agent SDK, fixtures demoted to test/CI only, durable Modal runtime + streaming UI + cost/injection hardening are all core scope. User accepted the loss of the fixture-keyed HMBP demo moment; record/replay (below) is the recommended mitigation for a flake-proof stage run.

## What this changes for the user

Today PermitPilot is a faithful simulation. The research workers return canned
`sourceFixtures`; the only live LLM in the repo is `gpt-4o-mini` in intake chat. A
viewer watching the trace panel sees a real multi-agent shape, but no agent ever
reads a real regulation. This plan makes the research workers do real work — each
`ResearchTask` becomes a Claude Agent SDK `query()` that fetches primary sources,
extracts quotes, and returns an `EvidenceBundle` — and moves the long-running
orchestration onto Modal so a real run can take minutes without hitting the Next
serverless timeout wall.

## Current state (verified against the code)

- `runLocalResearchPool(tasks, hypotheses)` at [workers.ts:4](../../../src/lib/research/workers.ts) is the single producer of `EvidenceBundle[]`. It branches on `USE_MODAL==="1"` to `runModalResearchPool`, else does an in-process fixture lookup via `fixtureForHypothesis`.
- Everything downstream consumes `EvidenceBundle` only: `verifyEvidence` ([verifier.ts:5](../../../src/lib/research/verifier.ts)), `synthesize`, the trace/matrix UI. **This is the seam.** No consumer needs to change.
- `runModalResearchPool` ([runModalPool.ts](../../../src/lib/research/modal/runModalPool.ts)) spawns `modal run worker.py --task-json {...}` per task via Node `child_process`, 30s timeout, greps `PERMITPILOT_BUNDLE_JSON {...}` from stdout. Real plumbing, **fake payload** — `worker.py` runs `echo` and returns fixtures ([worker.py:186](../../../src/lib/research/modal/worker.py)).
- `route.ts` POST awaits `runResearch` synchronously and returns the full `ResearchRun` ([run/route.ts](../../../app/api/research/run/route.ts)). Fine for ~instant fixture runs; a real multi-agent run blows past Vercel/Next serverless limits (~5 min, sometimes less).
- `ResearchTask` already carries the right knobs ([types.ts:86](../../../src/lib/research/types.ts)): `allowed_tools`, `blocked_tools`, `budget.{max_sources, max_runtime_seconds, max_model_calls}`. These map onto Agent SDK options.
- The scripted demo moment (`H-HAZMAT-HMBP` grounding-fail → repair ticket → re-pass) is keyed on `content_hash === "sha256:demo-hmbp-bad"` ([verifier.ts:12](../../../src/lib/research/verifier.ts)) — only a fixture emits that hash.
- No `@anthropic-ai/*` dependency exists. `codex` 0.118.0 and `modal` CLI are installed. No `.env` files in repo.

## Target architecture

The `EvidenceBundle` contract is the seam between the researcher subagents and the
orchestrator/verifier. Producers swap behind it; the consume side (verifier grounding,
synthesis) is generalized per Finding 1 and, in v1, synthesis moves *into* the
orchestrator agent (Decision 5).

```
POST /api/research/run
  -> enqueue run (return run_id, status=queued)        [API stays thin]
        |
        v
  run_research(run_id, input)        [v1: in-process; v2: durable Modal job]
     ORCHESTRATOR AGENT (system prompt)               [v1: agentic, per Decision 5]
        decompose: scope -> families -> hypotheses -> tasks   (was planResearch)
        curate per-subagent context (+ suggested skill via SKILL_FOR_HYPOTHESIS)
        -> research pool (strategy selector)
             fixture     : deterministic canned path        (test/CI)
             live_local  : Agent SDK query() per task, in-process    (v1)
             live_modal  : Agent SDK query() in the Modal function process (v2)
        -> verify (+repair)   [MECHANICAL backstop — not an agent]
        -> synthesize         [v1: BY the orchestrator agent; schema_gate + verifier gate it]
        -> write incremental state (trace, evidence, verdicts, determinations)
        |
        v
  GET /api/research/run/:id  -> poll status + partial artifacts   [v2 streams progress]
```

### Decision 1 — research strategy selector (replaces the `USE_MODAL` boolean)

Replace the `USE_MODAL` boolean with an explicit `RESEARCH_MODE` enum at the
`runLocalResearchPool` boundary:

- `fixture` (test/CI only after the swap): exactly today's behavior. Deterministic, free. No longer the demo path.
- `live_local` (**v1 live path**): real Agent SDK `query()` per task, run **in the orchestrating process** (in-process per D2). Dev + the v1 happy-path behind the flag.
- `live_modal` (v2 target): real Agent SDK `query()` run inside the **Modal function process** (in-process, per D2 — *not* a per-task Sandbox in v1). Per-task `modal.Sandbox` isolation is a v2 follow-up gated on the runtime spike.

Explicit enum over a boolean because there are now three real modes, and a new
contributor reads `RESEARCH_MODE=live_local` faster than decoding two booleans. Per
Decision 5 the same switch also governs the **orchestration** tier: `fixture` keeps the
deterministic `planResearch`/`synthesize`; live modes make the orchestrator agentic too.

### Decision 2 — the Agent SDK research worker

Each `ResearchTask` → one `query()` call. Mapping:

| ResearchTask field | Agent SDK option |
|---|---|
| `budget.max_model_calls` | `maxTurns` |
| `budget.max_runtime_seconds` | wall-clock `AbortController` timeout |
| `allowed_tools` (HarnessToolId[]) | `allowedTools` (after catalog→SDK tool-name mapping) |
| `blocked_tools` | `disallowedTools` |
| researcher steering | **just-in-time task context** (the `query()` prompt), *not* a per-role system prompt; thin/default `systemPrompt` |

The worker's final message must be JSON matching the `EvidenceBundle` schema. A
**schema gate** validates it before it enters the pipeline; on invalid JSON, emit a
`failedBundle` with `researcher_conclusion: "needs_review"` (the existing fail-closed
path). Tools the researcher actually needs: web fetch + web search (primary-source
retrieval), nothing that writes.

**Context-engineering note (user-directed architecture; supersedes the earlier "system prompt from `skillRegistry.ts`" idea).** Research subagents are a *contextual agentic team*, not personas — they do **not** each carry a bespoke system prompt. Per Anthropic's [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents), the standing "right-altitude" system prompts live only at the **intake** and **orchestration** tiers; `INTAKE_SYSTEM_PROMPT` ([prompt.ts:1](../../../src/lib/intake/prompt.ts)) is the only one that exists today. Each researcher is spawned by the orchestrator with **just-in-time curated context** — its `ResearchTask`, the target hypothesis, jurisdiction/source pointers, the minimal relevant intake facts, its allowed tools, and the `EvidenceBundle` output contract — under a thin/default `systemPrompt`. It works in an isolated context window and returns the `EvidenceBundle`, which *is* the "condensed, distilled summary (~1–2k tokens)" the article prescribes for subagents. The registry's `trigger`/`doneCondition` ([skillRegistry.ts:42](../../../src/lib/research/skillRegistry.ts)) are inputs the orchestrator folds into that per-task context, not a static persona. The second standing system prompt — the **orchestrator** — is authored in v1 (Decision 5).

**Tool-mapping caveat (independent review).** The `HarnessToolId`s in `toolCatalog.ts`
are *custom domain tool names* (a declarative contract), not Agent SDK built-ins. They
do **not** map 1:1 onto SDK tools like `WebFetch`/`WebSearch`. Two honest options:
(a) v1 — give the researcher the SDK's own `WebFetch`/`WebSearch` built-ins via
`allowedTools` and treat the catalog as documentation/policy, or (b) implement the
catalog tools as real SDK custom tools (MCP-style) and map names through. (a) is the
smaller v1; (b) is the "make the catalog load-bearing" version. This is a real decision,
not a rename — the Phase-2 "tool-name map" is closer to (a) than the table above implies.

### Decision 3 — durable Modal runtime

The current `modal run`-per-task CLI spawn is synchronous from Node, so it gives
isolation but **not** durability. For durability:

- Deploy the Modal app (`modal deploy`) with a web endpoint instead of CLI-spawning per task.
- `POST /api/research/run` calls the Modal endpoint to **spawn** the run (`Function.spawn()` / fire-and-forget), gets back a `run_id`, returns immediately with `status=queued`.
- The Modal function owns the full pipeline and writes incremental state.
- `GET /api/research/run/:id` reads state for polling/streaming.

### Decision 4 — run-state store (RESOLVED → `modal.Dict`)

Durability needs a store the API and Modal both reach. **Resolved at the gate → `modal.Dict`**:
- `modal.Dict` (**chosen, v1**) — no new infra, lives with the Modal app, right-sized for demo scale (one run at a time). The v1 UI polls `GET /:id`.
- Supabase Postgres (deferred) — a Supabase MCP is already configured here; durable, queryable, Realtime push for streaming. Migrate when run history / multi-user / Realtime is a real need (likely alongside the v2 streaming rewrite).

### Decision 5 — orchestration tier is an agentic LLM agent (RESOLVED → v1)

The context-engineering architecture puts a right-altitude system prompt at the **orchestration** tier. Today orchestration is *deterministic code* (`planResearch`/`run.ts`). **Resolved (user, 2026-05-31) → the orchestrator becomes a live LLM agent in v1**, not a v2 deferral. So v1 ships TWO standing system prompts — intake (exists) and the **new orchestrator prompt** — around the personaless researcher subagents.

The orchestrator agent owns three jobs (the article's "lead agent maintains the high-level plan… synthesizes results"):
- **Decompose:** scope → coverage families → hypotheses → research tasks (replaces deterministic `planResearch`).
- **Curate per-subagent context:** build each researcher's just-in-time payload, including the suggested skill via `SKILL_FOR_HYPOTHESIS` (Sub-project A).
- **Synthesize:** read returned `EvidenceBundle`s into the applicability matrix/determinations.

**What stays mechanical (NOT an agent):** the **verifier** is a deterministic backstop, not a persona — its grounding/currency/predicate checks (Finding 1) must be code so an agentic synthesizer can never reason its way past them. `schema_gate` + the verifier still gate the orchestrator's synthesized output.

**Mode interaction:** `RESEARCH_MODE=fixture` keeps BOTH tiers deterministic (today's `planResearch`/`synthesize`) for tests/CI; live modes make the orchestrator and researchers agentic together. One switch governs pipeline liveness, so `golden.ts`/vitest stay on the deterministic path.

**Finding 1 interaction:** an agentic synthesizer changes *how* the synthesis half of Finding 1 is solved (the orchestrator LLM reads bundles rather than us patching deterministic `appliesFor` in `synthesis.ts`) — but the **verifier-grounding half is unchanged and now even more load-bearing**, since the agentic synthesizer makes its own applicability calls that the mechanical verifier must independently ground-check before anything ships "verified".

## Demo-determinism — accepted tradeoff + mitigation

The premise gate chose the full production swap with eyes open: the scripted HMBP
fail→repair showpiece (keyed on `content_hash === "sha256:demo-hmbp-bad"`) will **not**
reproduce reliably once research is live, and a live multi-agent web run can exceed the
prior review's "under 90 seconds" target, cost API credits, and flake on stage Wi-Fi.
The fail-closed *behavior* survives (the verifier's grounding/predicate checks run for
real), but the rehearsed moment does not.

Mitigation (recommended, now core not stretch): a `record/replay` mode. Capture one
real live run's `EvidenceBundle`s + verdicts to a fixture-shaped recording, then replay
it deterministically on stage with real provenance (real URLs, real quotes, real
hashes). This is the honest way to demo "it's real" without depending on live Wi-Fi or
reproducing a probabilistic failure. It reuses the existing fixture-loading seam.

## Phased implementation

Ordering follows the independent review's "highest-risk-first": generalize the
consume side (Phase 2) and prove the SDK runtime (Phase 3 spike) *before* wiring a
live worker, because both can invalidate the whole approach and both are invisible if
you only test plumbing. Phases are split per the staged D1 decision.

**— v1 (de-risk + safe live happy-path) —**

1. **Dependency + config + test pinning.** Add `@anthropic-ai/claude-agent-sdk`. Add `RESEARCH_MODE` + `ANTHROPIC_API_KEY` to config with a typed reader, default `fixture`. **Re-pin `src/evals/golden.ts` and vitest to `fixture` mode** so the deterministic asserts keep holding after the default could otherwise change. No behavior change yet.
2. **Generalize the verifier consume side (do this FIRST, TDD).** Make `verifier.ts` grounding/predicate checks run for *any* bundle (real quote↔claim comparison, predicate math from `extracted_claims`) instead of the auto-pass default branch ([verifier.ts:106](../../../src/lib/research/verifier.ts)); generalize `repairEvidence` beyond HMBP; align verifier check-names to `confidence.ts`'s `FAIL_CAP` keys. (The synthesis half of Finding 1 is now handled by the agentic orchestrator in Phase 6, not by patching `synthesis.ts` — but deterministic `synthesize` stays as the `fixture`-mode path.) TDD against a deliberately-ungrounded live-shaped bundle first — this is Finding 1, the headline risk, and it is the backstop the agentic synthesizer (Phase 6) cannot bypass.
3. **SDK-runtime spike.** Prove `query()` actually runs in the target environment (it spawns the Claude Code CLI binary — Finding 6). Spike in-process first; only then decide per-task Modal Sandbox. Gates D-SDK-RUNTIME.
4. **Tool wiring (+ `read_skill`, Sub-project A).** Give the researcher the SDK's `WebFetch`/`WebSearch` built-ins via `allowedTools`; map/enforce `blocked_tools`→`disallowedTools`. **Add the `read_skill` tool** to `toolCatalog.ts` + `researcherCoreToolIds` + the `research` skill's `allowedToolIds` so the orchestrator stamps it into `allowed_tools`. Treat the rest of `toolCatalog.ts` as policy/docs for v1 (custom SDK tools are a follow-up — Decision 2 caveat). Unit-test the mapping.
5. **`live_local` researcher subagent (context-engineered).** Implement `run_research_agent`/`runLiveResearchTask` over a **pure `worker_core`** with injected `fetch_fn`/`extract_fn`/`read_skill_fn` (Sub-project A keeps the core testable). Assemble the **curated per-task context** (task + hypothesis + source pointers + minimal facts + tool set + `EvidenceBundle` schema) as the `query()` prompt under a thin/default `systemPrompt` — **no per-role persona**. Parse + schema-gate the returned bundle (the distilled summary), fail-closed on invalid output. Golden-eval one hypothesis end-to-end against the generalized verifier.
6. **Agentic orchestrator (Decision 5).** Author the orchestrator **system prompt** (the second standing prompt after intake). Replace `planResearch` decomposition with the agent (scope → families → hypotheses → tasks), curate each subagent's context (incl. the suggested skill via `SKILL_FOR_HYPOTHESIS`), and synthesize returned bundles into the applicability matrix. `schema_gate` + the **mechanical verifier (Phase 2)** gate its output; `fixture` mode keeps the deterministic `planResearch`/`synthesize` path for tests/CI.
7. **Injection + budget hardening.** Quarantine fetched web content, enforce per-task timeout + maxTurns + max_sources, add a global kill switch. (Security-critical; applies to both the orchestrator and researcher agents.)

**v1 constraint (durable Modal deferred):** because Phase 8 is v2, a v1 live run still goes through the synchronous `route.ts`. Keep v1 live runs inside the serverless window via tight budgets + small hypothesis N, or run them via the non-serverless path (`tsx` script / `golden.ts`-style harness) for dev. v2 removes this constraint. Note: v1 now runs TWO live LLM tiers (orchestrator + researchers) plus intake, so the cost/latency/credit profile is higher than a researcher-only swap — budget caps matter more.

**— v2 (durability + streaming, deferred per D1) —**

8. **Durable Modal runtime.** In-process Agent SDK worker inside the Modal *function* process (per D2); `modal deploy` web endpoint; `Function.spawn`-and-poll; incremental state to `modal.Dict` (per D3). Swap `route.ts` to enqueue + add `GET /:id`. (Per-task `modal.Sandbox` isolation only after a spike proves the CLI binary runs in-image.)
9. **UI incremental consumer (rewrite, not poll swap — Finding 5).** Replace the client-side `DELAYS_MS` replay engine ([useReplay.ts](../../../src/lib/ui/useReplay.ts)) with a store consumer that appends streamed events; fix `selectors.ts` per-task state + index-alignment for incremental/out-of-order writes.
10. **(Stretch) record/replay** mode for deterministic live demos.

## Sub-project A — EHS skills library + `read_skill` tool (v1)

A catalog-governed `read_skill` tool lets the researcher pull domain references on demand — the concrete realization of Decision 2's just-in-time context: the worker grounds extraction in real EHS rule knowledge instead of a baked persona or thin hints. No new infra.

**Guardrail (ties to Finding 1): skills orient, fetched sources ground.** A skill file is the *map* (what to look for, where, expected thresholds); the fetched primary regulation + verbatim quote is the *proof*. The generalized verifier (Phase 2) must still require a fetched source — citing a `SKILL.md` threshold as evidence is an ungrounded determination. Corollary: skill thresholds drift (rule amendments, CGP reissuance), so they are *expected ranges + the authoritative URL to verify against*, never a second source of truth.

**Components.**
- Skill files at `src/lib/research/skills/<id>/SKILL.md` (~5, one per coverage family), each with frontmatter (`id`, `description`, `when_to_use`) + Triggers / Thresholds table / Exemptions / authoritative source URLs (URLs MUST be allowlisted hosts): `scaqmd-air` (Rules 201/219/222, VOC) · `ca-stormwater` (CGP 1-acre, IGP SIC/NAICS) · `ca-hmbp` (55 gal / 500 lb / 200 cf) · `hazwaste-generator` (EPA VSQG/SQG/LQG) · `industrial-pretreatment` (EPA discharge triggers).
- New `read_skill` tool in `toolCatalog.ts` — its own `id`, `category: "knowledge_base_read"`, `writes: "none"`, `scopedTo: ["researcher"]` — added to `researcherCoreToolIds` + the `research` skill's `allowedToolIds`. NB: `knowledge_base_read` is a *category* that already exists ([toolCatalog.ts:14](../../../src/lib/research/toolCatalog.ts)); the new tool needs a distinct id.
- Worker integration: `run_research_agent` takes an injected `read_skill_fn(id)->str` (mirrors the planned `fetch_fn`/`extract_fn`, keeps `worker_core` pure/testable); `worker.py` provides the real reader (disk in `live_local`/v1, bundled image dir in `live_modal`/v2); a `SKILL_FOR_HYPOTHESIS` map surfaces the suggested skill id in the orchestrator's per-task context (Phase 6).

**Dependencies (what doesn't exist yet).** `worker_core`, `run_research_agent`, `fetch_fn`/`extract_fn`, `SKILL_FOR_HYPOTHESIS`, and a concrete **host allowlist** do not exist today (the current `worker.py` returns fixtures). So Sub-project A rides on the Phase-5 live-worker refactor. The 5 skills' canonical URLs already exist as fixtures in [worker.py:33-104](../../../src/lib/research/modal/worker.py) / [fixtures/sources.ts](../../../src/lib/research/fixtures/sources.ts) and map 1:1 to the skill ids — seed the allowlist from those hosts (`aqmd.gov`, `waterboards.ca.gov`, `calepa.ca.gov`, `epa.gov`).

**Coverage (resolved 2026-05-31 — no gap).** `land_use` is a `CoverageFamily` *type* value ([types.ts:19](../../../src/lib/research/types.ts)) but the planner never emits it: `planResearch` plans only over `coverageFamilies = ["air","stormwater","hazmat","waste","wastewater"]` ([planner.ts:11](../../../src/lib/research/planner.ts)). Those 5 map 1:1 to the 5 skills, and all 9 hypotheses the planner can produce (`H-AIR-201`/`-VOC`/`-219`/`-222`, `H-STORM-IGP`/`-CGP`, `H-HAZMAT-HMBP`, `H-WASTE-GENERATOR`, `H-WASTEWATER-PRETREATMENT`) resolve to one of them. **No 6th skill needed.** The parity test (below) keys off the planner's `coverageFamilies` array + emittable hypothesis ids — not the `CoverageFamily` type — so it stays green today and fails loudly if anyone later adds `land_use` (or any family) to the array without a skill or explicit null.

**Testing.** `worker_core`: `read_skill` dispatch returns injected content; researcher scope still enforced (no out-of-role tool reaches it). Parity test (keys off the planner's actual output, not the `CoverageFamily` type): every family in `coverageFamilies` ([planner.ts:11](../../../src/lib/research/planner.ts)) has a skill; every hypothesis id the planner can emit has a `SKILL_FOR_HYPOTHESIS` entry pointing at an existing skill file; every skill source URL is an allowlisted host. A family added to the planner without a skill then fails the test instead of silently going unskilled.

**Sequencing.** Skill content + host allowlist can start now (pure data, no worker dependency). `read_skill` catalog wiring rides Phase 4; `worker_core` injection + `SKILL_FOR_HYPOTHESIS` + tests ride Phases 5–6.

## Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Live run kills the deterministic demo moment | Lose the showpiece | Keep `fixture` default; record/replay for "real" demos |
| Real web research exceeds demo latency | Demo drags | Budget caps; subset live; cached/replay path |
| Prompt injection via fetched sources | Agent follows malicious page | Quarantine fetched content; read-only tool allowlist; verifier still gates |
| API cost per run | Burns credits in dev/demo | `fixture` default; budget caps; kill switch |
| Modal CLI-spawn brittleness | Flaky bridge | Move to deployed web endpoint, drop per-task `modal run` |

## Decisions (RESOLVED)

- **D-PREMISE:** RESOLVED → **Full production swap** is the destination; **sequencing is staged** (D1 below).
- **D1 (scope/sequencing):** RESOLVED → **Staged**. v1 = de-risk + safe live happy-path; v2 = durable Modal + UI streaming rewrite + record/replay. Chosen because the review surfaced feasibility (Finding 6) + ~3x blast radius unknowns after the premise was set.
- **D-STORE:** RESOLVED → **`modal.Dict`** for v1 (independent voice's pick over the auto-decided Supabase Postgres). No new infra; migrate to Postgres when history/multi-user/Realtime is real.
- **D-SDK-RUNTIME:** RESOLVED → **in-process SDK for v1** (independent voice's pick over the auto-decided per-task `live_modal` Sandbox). `query()` runs the Claude Code CLI binary (Finding 6); per-task sandbox isolation is a v2 follow-up gated on a spike.
- **D-CONTEXT-ENG (post-gate, 2026-05-31):** RESOLVED → research subagents are a personaless **contextual agentic team**; system prompts live only at the intake + orchestration tiers (per the context-engineering article). See Decision 2.
- **D5 (orchestration tier, post-gate, 2026-05-31):** RESOLVED → **agentic orchestrator in v1** (user chose v1 over the recommended v2). The orchestrator decomposes + curates subagent context + synthesizes; the verifier stays a mechanical backstop. See Decision 5.
- **Sub-project A (post-gate, 2026-05-31):** folded into v1 — EHS skills library + `read_skill` just-in-time tool. See the Sub-project A section.

## Engineering review (Eng phase)

Dual-voice note: codex CLI is UNAVAILABLE on this machine (0.118.0 defaults to model `gpt-5.5`, API-rejected; `-m gpt-5` rejected for ChatGPT-account auth; token-refresh failure). To preserve autoplan's independent second voice, an independent Claude subagent reviewed the plan + code cold. Findings 5–6, the repair/confidence additions to Finding 1, the Decision-2 tool caveat, and both auto-decision challenges below come from that review.

### Finding 1 (HEADLINE, highest risk) — the seam is clean for plumbing, fixture-coupled for semantics

`EvidenceBundle` at [workers.ts:4](../../../src/lib/research/workers.ts) is the right boundary for swapping the *producer*. But two downstream consumers do not read the agent's actual research result, so swapping the producer alone is not enough:

- **Verifier rubber-stamps the generic path.** [verifier.ts:106](../../../src/lib/research/verifier.ts) — the default branch returns `verdict: "pass"` with `grounding`/`predicate_math` hardcoded `pass: true` for any bundle whose `source.authority_rank <= 2`. The real grounding and threshold checks only exist for the special-cased demo hypothesis IDs (`H-HAZMAT-HMBP`, `H-STORM-CGP`, ...). A live bundle for any other hypothesis is auto-passed with no real grounding. For a compliance product that ships "verified: yes," this is a correctness and safety hole.
- **Synthesis ignores the agent's conclusion.** [synthesis.ts:73](../../../src/lib/research/synthesis.ts) `appliesFor` hardcodes applicability: `H-STORM-CGP` checks acres, everything else returns `"yes"`. It never reads `evidence.researcher_conclusion` or `extracted_claims`. `requirementFor`/`projectFactFor` are hardcoded maps over the 9 demo IDs. So even a perfect live finding is overwritten by scope-derived predicate logic keyed on demo IDs.
- **Repair is HMBP-only (independent review).** `repairEvidence` ([verifier.ts:121](../../../src/lib/research/verifier.ts)) only knows how to repair `H-HAZMAT-HMBP`; for any other hypothesis it returns an empty `needs_review`. So once research is live, the verify→repair→re-pass loop produces **dead repairs** for every non-HMBP hypothesis — the one behavior the demo is built to show off does not generalize.
- **Confidence is keyed on exact check-name strings (independent review).** `computeConfidence` ([confidence.ts:42](../../../src/lib/research/confidence.ts)) looks up `FAIL_CAP[name]` by the check's *name* (`currency`/`grounding`/`authority`/`predicate_math`/`cross_source`). A generalized verifier must emit checks under those exact names or every failure silently falls to `DEFAULT_FAIL_CAP` (0.6) — quietly wrong confidence on live bundles. (`cross_source` has a cap but the current verifier never emits it.)

Consequence: a full production swap **must also generalize the consume side to read live evidence** — verifier grounding (real quote↔claim comparison), predicate math from `extracted_claims`, applicability from `researcher_conclusion`, `repairEvidence` beyond HMBP, and verifier check-names aligned to `confidence.ts`. This is ~3 more files (`verifier.ts`, `synthesis.ts`, and the confidence/check-name contract) but conceptually the core of "make it real." It is invisible if you only test the plumbing. → Surfaced at the gate as a scope decision.

### Finding 2 — Agent SDK worker contract

Map `budget.max_model_calls`→`maxTurns`, `budget.max_runtime_seconds`→`AbortController` wall-clock, `allowed_tools`/`blocked_tools`→`allowedTools`/`disallowedTools` after a `HarnessToolId`→SDK-tool-name map (unit-tested against `toolCatalog.ts`). The SDK returns free text, so guarantee output with: JSON-only instruction + parse + schema-validate (zod) + ONE repair turn on invalid JSON, else `failedBundle` (the existing fail-closed path at [workers.ts:88](../../../src/lib/research/workers.ts)). Researcher tools are read-only (web fetch/search); nothing that writes.

### Finding 3 — durable Modal topology correction

The current bridge fans out at the TASK level: N separate `modal run` subprocesses spawned from Node ([runModalPool.ts:62](../../../src/lib/research/modal/runModalPool.ts)). That gives isolation but NOT durability — the Node/route process still awaits all N, so `route.ts` still hits the serverless timeout. Correct topology: ONE durable Modal job per RUN (`modal deploy` + web endpoint), `POST` calls it with `Function.spawn()` (fire-and-forget) and returns `run_id` immediately; the Modal job internally fans out to per-task sandboxes and writes incremental state; `GET /:id` polls. Replace stdout-marker parsing (`PERMITPILOT_BUNDLE_JSON`) with HTTP request/response to the deployed endpoint.

### Finding 4 — security

`ANTHROPIC_API_KEY` as a Modal Secret + server-only Next env (never `NEXT_PUBLIC_`). Injection quarantine on fetched source content before it reaches the model's reasoning (the toolCatalog already carries the concept). Enforce the read-only allowlist at the SDK level via `disallowedTools`. Per-task timeout + maxTurns + max_sources caps + a global kill switch / circuit breaker. The verifier stays the backstop — but only once Finding 1 is fixed.

### Finding 5 (independent review) — the UI is a replay engine, not a streaming consumer

Phase 9 ("UI incremental consumer") might look like a poll swap. It is closer to a rewrite:

- **`useReplay.ts` fakes streaming client-side.** [useReplay.ts:4](../../../src/lib/ui/useReplay.ts) holds a hardcoded `DELAYS_MS` table keyed on exact `actor/phase/status` strings and schedules `setTimeout`s over a run it *already has in full* ([useReplay.ts:33](../../../src/lib/ui/useReplay.ts) `[...run.trace_events]`). Real Modal streaming delivers events incrementally over the wire — the store no longer has the whole run up front, so the replay-timing engine has to be replaced by a real incremental-append consumer, not just re-pointed at a poll endpoint.
- **State is inferred from one global fan-out event pair.** `getHypothesisState` ([selectors.ts:97](../../../src/lib/ui/selectors.ts)) decides per-hypothesis running/verified from the single `research_pool/fanout/running|done` pair when no per-artifact events exist. Emitting granular per-task live events (which real workers will) changes that inference and the tile states.
- **Determinations bind to hypotheses by array index.** `hypothesisIdForDeterminationIndex` and `groupDeterminationsByFamily` ([selectors.ts:74](../../../src/lib/ui/selectors.ts), [selectors.ts:139](../../../src/lib/ui/selectors.ts)) assume `determinations[i]` ↔ `research_graph[i]`. Any incremental/out-of-order streamed write of determinations corrupts the drawers (evidence shown under the wrong hypothesis). Incremental writes must preserve positional alignment or switch to id-keyed lookup.

### Finding 6 (independent review, FEASIBILITY) — the SDK runs the Claude Code CLI under the hood

`@anthropic-ai/claude-agent-sdk` `query()` (the TypeScript SDK) does not hit the API
directly — it spawns and drives the Claude Code CLI/agent binary as a child process.
That makes the **`live_modal` "SDK inside a Modal Sandbox per task"** path (the plan's
auto-pick for D-SDK-RUNTIME) the single most unproven integration in this swap: it needs
the CLI binary + Node present and runnable inside the sandbox, env/secret plumbed
through, and the JSON result marshalled back out — none of which is spiked. The
independent voice recommends **running the SDK in the Modal function process for v1**
(in-process, fewer cold starts, no nested binary) and treating per-task sandbox
isolation as a follow-up once a thin spike proves `query()` runs in the target image.
→ This challenges the D-SDK-RUNTIME auto-decision; surfaced at the gate.

### Blast radius

Modified: `workers.ts`, `run.ts` (orchestration becomes agentic in live modes), `route.ts`, `verifier.ts` (generalize grounding + `repairEvidence` — the mechanical backstop), `confidence.ts` (check-name contract), `toolCatalog.ts` + `skillRegistry.ts` (`read_skill` tool + researcher scope), `modal/worker.py`, `modal/runModalPool.ts`, `package.json`, config; UI replay/selectors (`useReplay.ts`, `selectors.ts`, `sandboxState.ts`) for incremental events (v2); `src/evals/golden.ts` re-pinned to `fixture`. `synthesis.ts`/`planResearch` stay as the deterministic `fixture`-mode path; live decomposition + synthesis move into the orchestrator agent. New: orchestrator agent + its system prompt, pure `worker_core` + live researcher subagent, schema gate, tool-name map, `src/lib/research/skills/*` (5 `SKILL.md`) + host allowlist + `SKILL_FOR_HYPOTHESIS` (Sub-project A), Modal web endpoint, run-state store (`modal.Dict`), `GET /api/research/run/:id`, incremental-streaming store consumer (v2). Consumers that keep their shape but depend on semantics: the report/trace UI reading `ResearchRun`.

## GSTACK REVIEW REPORT

- Premise: RESOLVED at gate → full production swap (user overrode the mode-flagged recommendation).
- CEO/product lens: covered by the premise gate; the determinism tradeoff was named and accepted, record/replay added as mitigation.
- Eng lens: 6 findings above. Headline (Finding 1) = the *consume* side (verifier, synthesis, `repairEvidence`, confidence check-names) is fixture/demo-ID-coupled and must be generalized for the swap to be real. Finding 6 = feasibility: the SDK runs the Claude Code CLI binary, so `live_modal` per-task sandbox is unspiked.
- Design lens: backend change; UI impact is a replay-engine rewrite to consume incremental events (Phase 9, Finding 5), not a poll swap. No new screens.
- DX lens: net-new `@anthropic-ai/claude-agent-sdk` dep, `ANTHROPIC_API_KEY`, `RESEARCH_MODE` enum keeps `fixture` mode for free/instant dev + CI; `golden.ts` re-pinned to `fixture`.
- Independent voice: codex unavailable (model/auth) → an independent Claude subagent served as the second voice. It expanded Finding 1 (repair + confidence), added Findings 5–6, and challenged BOTH auto-decisions.
- Final gate (2026-05-30): user took all three independent-voice recommendations → **D1 staged**, **D-SDK-RUNTIME in-process for v1**, **D-STORE `modal.Dict`**. Both originally auto-decided picks (Supabase, `live_modal`) were overridden toward the leaner, de-risked v1.
- Post-gate refinements (2026-05-31): research subagents are personaless/context-engineered (D-CONTEXT-ENG); the **orchestrator is agentic in v1** (D5); **Sub-project A** (EHS skills + `read_skill`) folded into v1. These add a second live LLM tier to v1 — bigger than the leaner gate-approved v1, by explicit user choice; the determinism/cost note in the v1 constraint applies.
- v1 scope: generalize the mechanical verifier (grounding + repair + confidence, TDD first); spike the in-process SDK runtime; ship the context-engineered `live_local` researcher subagent + the `read_skill`/skills library (Sub-project A); author + wire the agentic orchestrator (decompose + curate + synthesize); harden injection/budget. v2: durable Modal (in-process, `modal.Dict`) + UI streaming rewrite + record/replay.
- Status: APPROVED — ready to implement v1 on a fresh branch when you are. No code written and no commits in this /autoplan run (plan artifact only).
