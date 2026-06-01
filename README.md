# PermitPilot — EHS Permit Research Swarm

An AI-native Environmental, Health & Safety (EHS) research system. Given a free-text
facility or project change, it produces a **defensible regulatory applicability
matrix**: every "this permit applies" row is backed by a current, verbatim-quoted
primary source, and anything that can't be grounded **fails closed to human review**
rather than guessing.

Scope today: **California** (SCAQMD air, CA stormwater IGP/CGP, CA HMBP, hazardous
waste generator status, wastewater pretreatment).

## How it works

```
intake (LLM, OpenAI) -> ScopePack (typed facts + missing_facts)
        |
        v
planResearch  - derives the hypothesis task list from the PROGRAM REGISTRY
        |        (single source of truth); each triggered program -> research tasks.
        |        No hardcoded family list, no fixed angle pool.
        v
research pool - one agentic worker per hypothesis (real fetch over an allowlist +
        |        LLM extraction, grounded against the fetched source). Fails closed
        |        when the backend is unavailable; never substitutes canned results.
        v
verifier      - ID-agnostic mechanical checks: currency, authority, grounding
        |        (claim quote must be a verbatim span of the source), predicate.
        |        Confidence < 0.9 or a grounding failure -> re-dispatch the researcher
        |        (bounded retry) until it verifies or converges to needs_review.
        v
completeness  - re-derives the EXPECTED program set from the registry x scope and
        |        flags any program never investigated (the recall floor).
        v
synthesis     - applicability matrix; a row is "verified" only at confidence >= 0.9.
```

Subagent memory is **artifact-driven**: each research result is written to an
`ArtifactStore`, so retries and resumed runs accumulate evidence instead of
starting cold.

## Key modules (`src/lib/research/`)

| File | Role |
| --- | --- |
| `scope.ts` | LLM intake -> typed `ScopePack` (fail-closed `emptyScope`) |
| `programRegistry.ts` | Single source of truth: one entry per permit program, with triggers, hypotheses, and authority URL |
| `planner.ts` | Registry-driven hypothesis task list |
| `workers.ts` / `modal/` | Real agentic research worker (fetch + ground + extract) |
| `verifier.ts` | ID-agnostic mechanical verification + repair tickets |
| `confidence.ts` | `computeConfidence` (cap-don't-average) + the 0.9 synthesis gate |
| `completeness.ts` | Recall floor — catches wholly-missed programs |
| `artifactStore.ts` | Artifact-driven subagent memory |
| `synthesis.ts` | Applicability matrix + determinations |
| `toolCatalog.ts` | Role-scoped agent tools (incl. VOC/chemical analysis) |
| `skills/<id>/SKILL.md` | Per-program orientation docs (read by researchers; never citable evidence) |

## Design invariants

- **Nothing for show.** No fixture/canned research path; tests drive the real
  pipeline via an injected transport.
- **Verifier owns truth, mechanically.** No per-hypothesis-ID rubber-stamping; a
  determination is only "verified" when its quote is a verbatim span of a current,
  high-authority source and confidence >= 0.9.
- **Fail closed.** Missing facts, unreachable sources, and low confidence become
  `needs_review` — never a guessed "applies".
- **Registry is the source of truth.** Skills and the recall floor are projections
  of it; adding a program to the registry adds it to the plan.

## Running locally

```bash
npm install
npm run dev          # Next dev server
npm run test         # vitest
npm run typecheck    # tsc --noEmit
npm run eval         # golden cases + adversarial grounding eval (CI-gated)
```

Environment:
- `OPENAI_API_KEY` — intake + scope extraction (omit -> fail-closed `emptyScope`).
- `MODAL_RESEARCH_ENDPOINT` / `MODAL_RESEARCH_TOKEN` — the live research worker
  (omit -> research fails closed to `needs_review`; the pipeline still runs).
- `RAINDROP_LOCAL_DEBUGGER` — optional trace debugging (silent when unset).

## Repository hygiene

- Never commit API keys, `.env` files, or customer data.
- Treat final determinations as **human-review research support — not legal advice
  or autonomous filing.**

Planning/design history lives in [`docs/archive/`](./docs/archive/).
