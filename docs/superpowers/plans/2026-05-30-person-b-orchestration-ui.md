# Person B Orchestration UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Person B lane for the hackathon demo: orchestration-facing UI, research graph, trace panel, applicability matrix, evidence drawer, and demo flow around the verifier failure and repair moment.

**Architecture:** Build the UI against a local `ResearchRun` fixture first, then swap the data source to `POST /api/research/run` when Person A's endpoint is ready. The screen should render the product immediately: scenario input, graph, trace, verification summary, matrix, evidence drawer, and report. The graph must show `CoverageFamily -> RegulatoryAngle -> ResearchHypothesis -> ResearchTask`, because coverage families are completeness guards, not final checklist rows.

**Tech Stack:** Next.js App Router in `web/`, TypeScript, React, Tailwind CSS or plain CSS modules, and local JSON/TS fixtures until the API exists.

---

## Context

The remote design doc currently says the original split was user = Person A and teammate = Person B. The latest instruction is that you are working on B, so this plan treats you as Person B.

Remote GitHub has newer design material than the local checkout:

- `HACKATHON_DEMO_DESIGN.md` now emphasizes coverage-family inspection before hypothesis creation.
- `TEAM_SHARE_PACKET.md` references `TWO_PERSON_BUILD_SPLIT.md`.
- `TWO_PERSON_BUILD_SPLIT.md` defines the B lane in detail, but it is not present in the local checkout yet.

Before implementation, either pull the latest repo after preserving local edits, or copy the remote `TWO_PERSON_BUILD_SPLIT.md` into the workspace.

## File Structure

- Create: `web/package.json`
- Create: `web/src/app/page.tsx`
- Create: `web/src/app/layout.tsx`
- Create: `web/src/app/globals.css`
- Create: `web/src/lib/researchTypes.ts`
- Create: `web/src/lib/demoResearchRun.ts`
- Create: `web/src/lib/researchSelectors.ts` — pure functions that nest the 4-level graph and resolve evidence by `hypothesis_id`. The components stay dumb; this file holds the logic worth testing.
- Create: `web/src/lib/researchSelectors.test.ts` — vitest unit tests for the selectors, run against `demoResearchRun`.
- Create: `web/src/lib/runResearch.ts` — API client with fixture fallback.
- Create: `web/src/components/ProjectInput.tsx`
- Create: `web/src/components/ResearchGraph.tsx`
- Create: `web/src/components/TracePanel.tsx`
- Create: `web/src/components/VerificationSummary.tsx`
- Create: `web/src/components/ApplicabilityMatrix.tsx`
- Create: `web/src/components/EvidenceDrawer.tsx`
- Create: `web/src/components/ReportPanel.tsx`
- Later modify: `web/src/app/page.tsx` to call `POST /api/research/run` when Person A ships it.

Responsibility boundary: `researchSelectors.ts` owns all derivation (tree nesting, worker count, drawer resolution) so each component is a thin renderer. This keeps the testable logic in one focused file and the JSX trivial.

## Contract Questions For Person A

Ask these before or during Task 2:

- Should `Determination` include `hypothesis_id`? B needs a stable link from matrix row to evidence, verdict, and repair history.
- Should `TraceEvent.status` include `verified` and `repaired`, or should B derive those from message and artifact data?
- Will `/api/research/run` return partial data on failure, or only a terminal error?
- What field marks cached fixture replay versus live Modal worker execution?

### Task 1: Create The UI Scaffold

**Files:**
- Create: `web/package.json`
- Create: `web/src/app/layout.tsx`
- Create: `web/src/app/globals.css`
- Create: `web/src/app/page.tsx`

- [ ] **Step 1: Generate the app shell**

Run:

```bash
npx create-next-app@latest web --typescript --eslint --app --src-dir --tailwind --use-npm --import-alias "@/*"
```

Expected: a runnable Next.js app exists under `web/`.

- [ ] **Step 2: Start the dev server**

Run:

```bash
cd web
npm run dev
```

Expected: Next.js prints a localhost URL, usually `http://localhost:3000`.

- [ ] **Step 3: Replace the default landing page**

Create `web/src/app/page.tsx` with a temporary product shell:

```tsx
export default function Home() {
  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <section className="mx-auto grid max-w-7xl gap-4 p-4 lg:grid-cols-[320px_minmax(0,1fr)_320px]">
        <div className="rounded border border-slate-800 bg-slate-900 p-4">Project input</div>
        <div className="rounded border border-slate-800 bg-slate-900 p-4">Research graph and trace</div>
        <div className="rounded border border-slate-800 bg-slate-900 p-4">Verification summary</div>
        <div className="rounded border border-slate-800 bg-slate-900 p-4 lg:col-span-3">Applicability matrix</div>
      </section>
    </main>
  );
}
```

- [ ] **Step 4: Verify the first screen is product-first**

Run:

```bash
cd web
npm run dev
```

Expected: the first viewport shows the tool surface, not a marketing hero.

### Task 2: Add Shared Research Types

**Files:**
- Create: `web/src/lib/researchTypes.ts`

- [ ] **Step 1: Add the shared B-facing contract**

Create `web/src/lib/researchTypes.ts`:

```ts
export type RunStatus = "idle" | "queued" | "running" | "partial" | "needs_review" | "done" | "failed";

export type CoverageFamily =
  | "air"
  | "stormwater"
  | "hazmat"
  | "waste"
  | "wastewater"
  | "land_use"
  | "fire_code"
  | "ceqa"
  | "osha";

export type CoverageFamilyStatus = {
  id: string;
  family: CoverageFamily;
  status: "active" | "blocked_missing_fact" | "out_of_scope" | "discovery_candidate";
  reason: string;
  project_facts_considered: string[];
  missing_facts: string[];
};

export type RegulatoryAngle = {
  id: string;
  family: CoverageFamily;
  label: string;
  reason: string;
  triggering_facts: string[];
  status: "active" | "blocked_missing_fact" | "out_of_scope" | "discovery_candidate";
};

export type ResearchHypothesis = {
  id: string;
  angle_id: string;
  question: string;
  claim_to_test?: string;
  required_facts: string[];
  expected_source_type: "statute" | "regulation" | "agency_guidance" | "permit_portal" | "technical_doc";
  success_criteria: string[];
  dependencies: string[];
};

export type ResearchTask = {
  task_id: string;
  hypothesis_id: string;
  assigned_agent: string;
  allowed_tools: string[];
  blocked_tools: string[];
  budget: {
    max_sources: number;
    max_runtime_seconds: number;
    max_model_calls: number;
  };
};

export type EvidenceBundle = {
  hypothesis_id: string;
  sources: Array<{
    url: string;
    source_name: string;
    authority_rank: number;
    fetched_at: string;
    content_hash: string;
    effective_date: string | null;
    quote: string;
  }>;
  extracted_claims: Array<{
    field: string;
    value: string;
    source_url: string;
    quote: string;
    confidence: number;
  }>;
  researcher_conclusion: "applies" | "does_not_apply" | "needs_review";
  uncertainties: string[];
};

export type RepairTicket = {
  ticket_id: string;
  hypothesis_id: string;
  failure_type: "grounding_failed" | "source_failed" | "missing_fact" | "invalid_json" | "conflict";
  failed_check: string;
  observed_problem: string;
  repair_action: string;
  max_attempts_remaining: number;
};

export type VerificationVerdict = {
  hypothesis_id: string;
  verdict: "pass" | "fail" | "needs_review";
  checks: Record<string, { pass: boolean; reason: string }>;
  confidence: number;
  repair_tickets: RepairTicket[];
};

export type Determination = {
  requirement: string;
  applies: "yes" | "no" | "needs_review";
  trigger: string;
  project_fact: string;
  citation: string;
  quote: string;
  source_url: string;
  confidence: number;
  verified: boolean;
  review_flag: boolean;
  hypothesis_id?: string;
};

export type TraceEvent = {
  id: string;
  run_id: string;
  ts: string;
  actor: string;
  phase: string;
  status: "queued" | "running" | "done" | "failed" | "needs_review";
  message: string;
  artifact_id?: string;
};

export type ResearchRun = {
  run_id: string;
  status: RunStatus;
  project_facts: Record<string, unknown>;
  jurisdiction_stack: string[];
  coverage_family_statuses: CoverageFamilyStatus[];
  regulatory_angles: RegulatoryAngle[];
  research_graph: ResearchHypothesis[];
  research_tasks: ResearchTask[];
  evidence_bundles: EvidenceBundle[];
  verification_verdicts: VerificationVerdict[];
  repair_tickets: RepairTicket[];
  determinations: Determination[];
  trace_events: TraceEvent[];
  report_markdown: string;
};
```

- [ ] **Step 2: Type-check**

Run:

```bash
cd web
npm run lint
```

Expected: lint passes or reports only default scaffold issues.

### Task 3: Add A Demo `ResearchRun` Fixture

**Files:**
- Create: `web/src/lib/demoResearchRun.ts`

- [ ] **Step 1: Add a fixture that proves the B surface**

Create `web/src/lib/demoResearchRun.ts`:

```ts
import type { ResearchRun } from "./researchTypes";

export const demoResearchRun: ResearchRun = {
  run_id: "run_socal_coating_demo",
  status: "done",
  project_facts: {
    facility: "Los Angeles County manufacturing facility",
    naics: "332813",
    sic: "3471",
    equipment: "new coating booth",
    chemical: "60 gallons flammable solvent",
    waste_stream: "spent solvent, monthly quantity missing",
    disturbance_acres: 0,
  },
  jurisdiction_stack: ["SCAQMD", "California Water Boards", "Local CUPA"],
  coverage_family_statuses: [
    {
      id: "CF-AIR",
      family: "air",
      status: "active",
      reason: "The project adds a coating booth that may be new emitting equipment.",
      project_facts_considered: ["new coating booth", "SCAQMD jurisdiction"],
      missing_facts: [],
    },
    {
      id: "CF-STORM",
      family: "stormwater",
      status: "active",
      reason: "The facility has SIC/NAICS facts that may map to industrial stormwater coverage.",
      project_facts_considered: ["SIC 3471", "NAICS 332813", "0 acres disturbed"],
      missing_facts: [],
    },
    {
      id: "CF-HAZMAT",
      family: "hazmat",
      status: "active",
      reason: "The project stores 60 gallons of hazardous liquid.",
      project_facts_considered: ["60 gallons flammable solvent"],
      missing_facts: [],
    },
    {
      id: "CF-WASTE",
      family: "waste",
      status: "blocked_missing_fact",
      reason: "Spent solvent is present, but monthly generation quantity is missing.",
      project_facts_considered: ["spent solvent"],
      missing_facts: ["kg_per_month"],
    },
    {
      id: "CF-WASTEWATER",
      family: "wastewater",
      status: "out_of_scope",
      reason: "No process wastewater discharge fact was provided in the seeded scenario.",
      project_facts_considered: ["no discharge described"],
      missing_facts: [],
    },
  ],
  regulatory_angles: [
    {
      id: "A-AIR-EMITTING-EQUIPMENT",
      family: "air",
      label: "New or modified emitting equipment",
      reason: "A coating booth may emit regulated pollutants and require authorization.",
      triggering_facts: ["coating booth", "SCAQMD jurisdiction"],
      status: "active",
    },
    {
      id: "A-HAZMAT-HMBP",
      family: "hazmat",
      label: "Hazardous material business plan threshold",
      reason: "The stored liquid quantity is near a known gallon threshold.",
      triggering_facts: ["60 gallons flammable solvent"],
      status: "active",
    },
    {
      id: "A-WASTE-GENERATOR",
      family: "waste",
      label: "Hazardous waste generator status",
      reason: "Spent solvent exists, but monthly generation quantity is missing.",
      triggering_facts: ["spent solvent"],
      status: "blocked_missing_fact",
    },
  ],
  research_graph: [
    {
      id: "H-AIR-001",
      angle_id: "A-AIR-EMITTING-EQUIPMENT",
      question: "Does the new coating booth require an SCAQMD Permit to Construct?",
      claim_to_test: "The coating booth may require SCAQMD authorization before installation.",
      required_facts: ["equipment type", "jurisdiction", "emissions or exemption facts"],
      expected_source_type: "regulation",
      success_criteria: ["official source", "trigger quote", "human-review fallback"],
      dependencies: [],
    },
    {
      id: "H-HAZMAT-001",
      angle_id: "A-HAZMAT-HMBP",
      question: "Does 60 gallons of hazardous liquid trigger HMBP/CERS obligations?",
      claim_to_test: "HMBP applies because 60 gallons is above the 55 gallon threshold.",
      required_facts: ["chemical quantity", "unit", "hazard class"],
      expected_source_type: "agency_guidance",
      success_criteria: ["official source", "threshold quote", "math check"],
      dependencies: [],
    },
    {
      id: "H-WASTE-001",
      angle_id: "A-WASTE-GENERATOR",
      question: "Can generator status be determined without monthly spent solvent quantity?",
      required_facts: ["kg_per_month"],
      expected_source_type: "regulation",
      success_criteria: ["missing-fact blocker remains visible"],
      dependencies: [],
    },
  ],
  research_tasks: [
    {
      task_id: "T-AIR-001",
      hypothesis_id: "H-AIR-001",
      assigned_agent: "air_researcher",
      allowed_tools: ["official_web_fetch", "pdf_extract", "citation_extractor"],
      blocked_tools: ["memory_write", "final_report_write"],
      budget: { max_sources: 5, max_runtime_seconds: 90, max_model_calls: 6 },
    },
    {
      task_id: "T-HAZMAT-001",
      hypothesis_id: "H-HAZMAT-001",
      assigned_agent: "hazmat_researcher",
      allowed_tools: ["official_web_fetch", "citation_extractor", "predicate_math"],
      blocked_tools: ["memory_write", "final_report_write"],
      budget: { max_sources: 4, max_runtime_seconds: 90, max_model_calls: 6 },
    },
    {
      task_id: "T-WASTE-001",
      hypothesis_id: "H-WASTE-001",
      assigned_agent: "waste_researcher",
      allowed_tools: ["missing_fact_detector"],
      blocked_tools: ["memory_write", "final_report_write"],
      budget: { max_sources: 2, max_runtime_seconds: 45, max_model_calls: 3 },
    },
  ],
  evidence_bundles: [
    {
      hypothesis_id: "H-HAZMAT-001",
      sources: [
        {
          url: "https://cers.calepa.ca.gov/",
          source_name: "California CERS hazardous materials guidance",
          authority_rank: 1,
          fetched_at: "2026-05-30T10:00:00Z",
          content_hash: "sha256:demo-hmbp-threshold",
          effective_date: null,
          quote: "Businesses must submit information for hazardous materials at or above threshold quantities.",
        },
      ],
      extracted_claims: [
        {
          field: "initial_claim",
          value: "HMBP applies to all hazardous material storage.",
          source_url: "https://cers.calepa.ca.gov/",
          quote: "Businesses must submit information for hazardous materials at or above threshold quantities.",
          confidence: 0.62,
        },
        {
          field: "repaired_threshold",
          value: "60 gallons is above the 55 gallon hazardous liquid threshold.",
          source_url: "https://cers.calepa.ca.gov/",
          quote: "Businesses must submit information for hazardous materials at or above threshold quantities.",
          confidence: 0.88,
        },
      ],
      researcher_conclusion: "applies",
      uncertainties: [],
    },
  ],
  verification_verdicts: [
    {
      hypothesis_id: "H-HAZMAT-001",
      verdict: "pass",
      checks: {
        authority: { pass: true, reason: "Official California reporting system source." },
        grounding_initial: { pass: false, reason: "The quote mentions thresholds, not all storage." },
        grounding_repaired: { pass: true, reason: "The repaired claim compares customer quantity to threshold." },
        predicate_math: { pass: true, reason: "60 gallons is greater than 55 gallons." },
      },
      confidence: 0.88,
      repair_tickets: [],
    },
    {
      hypothesis_id: "H-WASTE-001",
      verdict: "needs_review",
      checks: {
        missing_facts: { pass: false, reason: "Monthly spent solvent quantity is missing." },
      },
      confidence: 0.41,
      repair_tickets: [],
    },
  ],
  repair_tickets: [
    {
      ticket_id: "R-HAZMAT-001",
      hypothesis_id: "H-HAZMAT-001",
      failure_type: "grounding_failed",
      failed_check: "grounding_initial",
      observed_problem: "The extracted claim said all storage, but the quote only supports threshold-based reporting.",
      repair_action: "Rerun extraction with quote-constrained threshold comparison.",
      max_attempts_remaining: 1,
    },
  ],
  determinations: [
    {
      requirement: "HMBP/CERS hazardous materials reporting",
      applies: "yes",
      trigger: "Hazardous liquid quantity exceeds threshold",
      project_fact: "60 gallons flammable solvent",
      citation: "California CERS threshold guidance",
      quote: "Businesses must submit information for hazardous materials at or above threshold quantities.",
      source_url: "https://cers.calepa.ca.gov/",
      confidence: 0.88,
      verified: true,
      review_flag: false,
      hypothesis_id: "H-HAZMAT-001",
    },
    {
      requirement: "Hazardous waste generator status",
      applies: "needs_review",
      trigger: "Spent solvent waste stream",
      project_fact: "Monthly quantity missing",
      citation: "Missing fact",
      quote: "Monthly spent solvent generation quantity is required before status can be determined.",
      source_url: "",
      confidence: 0.41,
      verified: false,
      review_flag: true,
      hypothesis_id: "H-WASTE-001",
    },
  ],
  trace_events: [
    {
      id: "EVT-001",
      run_id: "run_socal_coating_demo",
      ts: "2026-05-30T10:00:00Z",
      actor: "Scope Agent",
      phase: "scope",
      status: "done",
      message: "ScopePack created for Los Angeles County manufacturing facility.",
    },
    {
      id: "EVT-002",
      run_id: "run_socal_coating_demo",
      ts: "2026-05-30T10:00:02Z",
      actor: "Orchestrator",
      phase: "planning",
      status: "done",
      message: "Coverage floor inspected air, stormwater, hazmat, waste, and wastewater.",
    },
    {
      id: "EVT-003",
      run_id: "run_socal_coating_demo",
      ts: "2026-05-30T10:00:04Z",
      actor: "Worker Pool",
      phase: "research",
      status: "running",
      message: "3 demo research workers spawned from scoped task graph.",
    },
    {
      id: "EVT-004",
      run_id: "run_socal_coating_demo",
      ts: "2026-05-30T10:00:12Z",
      actor: "Verifier",
      phase: "verification",
      status: "failed",
      message: "HMBP grounding failed: quote did not support all-storage claim.",
      artifact_id: "R-HAZMAT-001",
    },
    {
      id: "EVT-005",
      run_id: "run_socal_coating_demo",
      ts: "2026-05-30T10:00:16Z",
      actor: "Orchestrator",
      phase: "repair",
      status: "done",
      message: "RepairTicket created and scoped threshold extraction rerun.",
      artifact_id: "R-HAZMAT-001",
    },
    {
      id: "EVT-006",
      run_id: "run_socal_coating_demo",
      ts: "2026-05-30T10:00:24Z",
      actor: "Synthesis Agent",
      phase: "matrix",
      status: "done",
      message: "Final matrix created with verified HMBP row and waste needs-review row.",
    },
  ],
  report_markdown:
    "The seeded facility change triggered a dynamic research graph across air, stormwater, hazmat, waste, and wastewater. The HMBP row was repaired after the verifier rejected an overbroad claim. Hazardous waste generator status remains needs-review because monthly waste quantity is missing.",
};
```

- [ ] **Step 2: Type-check the fixture**

Run:

```bash
cd web
npm run lint
```

Expected: TypeScript accepts `demoResearchRun` as a complete `ResearchRun`.

### Task 4: Build And Test The Graph + Evidence Selectors (TDD)

The graph-nesting logic and the drawer's evidence lookup are the only non-trivial logic in the B lane. Extract them into pure functions and test them against the fixture before any component renders them. The components in Task 5 import these and stay trivial.

**Files:**
- Create: `web/src/lib/researchSelectors.ts`
- Test: `web/src/lib/researchSelectors.test.ts`

- [ ] **Step 1: Add a test runner**

Run:

```bash
cd web
npm install -D vitest
```

Then add a `test` script to `web/package.json` `"scripts"`:

```json
"test": "vitest run"
```

Expected: `npx vitest run` is available. Vitest runs TypeScript with no extra config because the selectors are pure (no JSX).

- [ ] **Step 2: Write the failing selector tests**

Create `web/src/lib/researchSelectors.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { demoResearchRun } from "./demoResearchRun";
import { buildCoverageTree, buildEvidenceView, getWorkerCount } from "./researchSelectors";

describe("buildCoverageTree", () => {
  it("returns one node per coverage family status, in order", () => {
    const tree = buildCoverageTree(demoResearchRun);
    expect(tree).toHaveLength(5);
    expect(tree.map((f) => f.family)).toEqual([
      "air",
      "stormwater",
      "hazmat",
      "waste",
      "wastewater",
    ]);
  });

  it("nests angle -> hypothesis -> task under the right family", () => {
    const tree = buildCoverageTree(demoResearchRun);
    const hazmat = tree.find((f) => f.family === "hazmat");
    expect(hazmat?.angles).toHaveLength(1);

    const angle = hazmat?.angles[0];
    expect(angle?.id).toBe("A-HAZMAT-HMBP");
    expect(angle?.hypotheses).toHaveLength(1);

    const hypothesis = angle?.hypotheses[0];
    expect(hypothesis?.id).toBe("H-HAZMAT-001");
    expect(hypothesis?.tasks).toHaveLength(1);
    expect(hypothesis?.tasks[0].task_id).toBe("T-HAZMAT-001");
  });

  it("keeps a family with no angles visible as an empty branch", () => {
    const tree = buildCoverageTree(demoResearchRun);
    const wastewater = tree.find((f) => f.family === "wastewater");
    expect(wastewater?.status).toBe("out_of_scope");
    expect(wastewater?.angles).toHaveLength(0);
  });
});

describe("getWorkerCount", () => {
  it("derives worker count from the scoped task graph, not a fixed team", () => {
    expect(getWorkerCount(demoResearchRun)).toBe(demoResearchRun.research_tasks.length);
    expect(getWorkerCount(demoResearchRun)).toBe(3);
  });
});

describe("buildEvidenceView", () => {
  it("resolves evidence, verdict, and repair history by hypothesis_id", () => {
    const hmbp = demoResearchRun.determinations.find((d) => d.hypothesis_id === "H-HAZMAT-001");
    expect(hmbp).toBeDefined();

    const view = buildEvidenceView(demoResearchRun, hmbp!);
    expect(view.evidence?.hypothesis_id).toBe("H-HAZMAT-001");
    expect(view.verdict?.verdict).toBe("pass");
    expect(view.repairs).toHaveLength(1);
    expect(view.repairs[0].failure_type).toBe("grounding_failed");
  });

  it("returns empty evidence for a determination with no hypothesis link", () => {
    const orphan = { ...demoResearchRun.determinations[0], hypothesis_id: undefined };
    const view = buildEvidenceView(demoResearchRun, orphan);
    expect(view.evidence).toBeUndefined();
    expect(view.repairs).toHaveLength(0);
  });
});
```

- [ ] **Step 3: Run the tests to verify they fail**

Run:

```bash
cd web
npx vitest run src/lib/researchSelectors.test.ts
```

Expected: FAIL with "does not provide an export named 'buildCoverageTree'" (the module does not exist yet).

- [ ] **Step 4: Implement the selectors**

Create `web/src/lib/researchSelectors.ts`:

```ts
import type {
  CoverageFamily,
  CoverageFamilyStatus,
  Determination,
  EvidenceBundle,
  RegulatoryAngle,
  RepairTicket,
  ResearchHypothesis,
  ResearchRun,
  ResearchTask,
  VerificationVerdict,
} from "./researchTypes";

export type GraphHypothesisNode = ResearchHypothesis & { tasks: ResearchTask[] };
export type GraphAngleNode = RegulatoryAngle & { hypotheses: GraphHypothesisNode[] };
export type GraphFamilyNode = CoverageFamilyStatus & { angles: GraphAngleNode[] };

export function buildCoverageTree(run: ResearchRun): GraphFamilyNode[] {
  const tasksByHypothesis = new Map<string, ResearchTask[]>();
  for (const task of run.research_tasks) {
    const list = tasksByHypothesis.get(task.hypothesis_id) ?? [];
    list.push(task);
    tasksByHypothesis.set(task.hypothesis_id, list);
  }

  const hypothesesByAngle = new Map<string, GraphHypothesisNode[]>();
  for (const hypothesis of run.research_graph) {
    const node: GraphHypothesisNode = {
      ...hypothesis,
      tasks: tasksByHypothesis.get(hypothesis.id) ?? [],
    };
    const list = hypothesesByAngle.get(hypothesis.angle_id) ?? [];
    list.push(node);
    hypothesesByAngle.set(hypothesis.angle_id, list);
  }

  const anglesByFamily = new Map<CoverageFamily, GraphAngleNode[]>();
  for (const angle of run.regulatory_angles) {
    const node: GraphAngleNode = {
      ...angle,
      hypotheses: hypothesesByAngle.get(angle.id) ?? [],
    };
    const list = anglesByFamily.get(angle.family) ?? [];
    list.push(node);
    anglesByFamily.set(angle.family, list);
  }

  return run.coverage_family_statuses.map((family) => ({
    ...family,
    angles: anglesByFamily.get(family.family) ?? [],
  }));
}

export function getWorkerCount(run: ResearchRun): number {
  return run.research_tasks.length;
}

export function getEvidenceForHypothesis(
  run: ResearchRun,
  hypothesisId: string,
): EvidenceBundle | undefined {
  return run.evidence_bundles.find((bundle) => bundle.hypothesis_id === hypothesisId);
}

export function getVerdictForHypothesis(
  run: ResearchRun,
  hypothesisId: string,
): VerificationVerdict | undefined {
  return run.verification_verdicts.find((verdict) => verdict.hypothesis_id === hypothesisId);
}

export function getRepairsForHypothesis(run: ResearchRun, hypothesisId: string): RepairTicket[] {
  return run.repair_tickets.filter((ticket) => ticket.hypothesis_id === hypothesisId);
}

export type EvidenceView = {
  determination: Determination;
  evidence?: EvidenceBundle;
  verdict?: VerificationVerdict;
  repairs: RepairTicket[];
};

export function buildEvidenceView(run: ResearchRun, determination: Determination): EvidenceView {
  const id = determination.hypothesis_id;
  return {
    determination,
    evidence: id ? getEvidenceForHypothesis(run, id) : undefined,
    verdict: id ? getVerdictForHypothesis(run, id) : undefined,
    repairs: id ? getRepairsForHypothesis(run, id) : [],
  };
}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
cd web
npx vitest run src/lib/researchSelectors.test.ts
```

Expected: PASS, all selector tests green.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/researchSelectors.ts web/src/lib/researchSelectors.test.ts web/package.json web/package-lock.json
git commit -m "feat: graph + evidence selectors with tests"
```

### Task 5: Build The Product Screen From Fixture Data

**Files:**
- Modify: `web/src/app/page.tsx`
- Create: `web/src/components/ProjectInput.tsx`
- Create: `web/src/components/ResearchGraph.tsx`
- Create: `web/src/components/TracePanel.tsx`
- Create: `web/src/components/VerificationSummary.tsx`
- Create: `web/src/components/ApplicabilityMatrix.tsx`
- Create: `web/src/components/EvidenceDrawer.tsx`
- Create: `web/src/components/ReportPanel.tsx`

- [ ] **Step 1: Build the project input component**

Create `web/src/components/ProjectInput.tsx`:

```tsx
"use client";

import type { RunStatus } from "@/lib/researchTypes";

type Props = {
  value: string;
  onChange: (value: string) => void;
  onLoadDemo: () => void;
  onRun: () => void;
  isRunning: boolean;
  runStatus: RunStatus;
};

export function ProjectInput({ value, onChange, onLoadDemo, onRun, isRunning, runStatus }: Props) {
  return (
    <div className="flex flex-col gap-3 rounded border border-slate-800 bg-slate-900 p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Project change</h2>
      <textarea
        className="min-h-32 resize-y rounded border border-slate-700 bg-slate-950 p-2 text-sm text-slate-100"
        placeholder="Describe the facility change..."
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        type="button"
        onClick={onLoadDemo}
        className="rounded border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800"
      >
        Load SoCal manufacturing demo
      </button>
      <button
        type="button"
        onClick={onRun}
        disabled={isRunning || value.trim().length === 0}
        className="rounded bg-emerald-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"
      >
        {isRunning ? "Running..." : "Run research swarm"}
      </button>
      <p className="text-xs text-slate-500">Run status: {runStatus}</p>
    </div>
  );
}
```

- [ ] **Step 2: Build the research graph component**

Create `web/src/components/ResearchGraph.tsx`. It renders the full `CoverageFamily -> RegulatoryAngle -> ResearchHypothesis -> ResearchTask` nest from `buildCoverageTree`, so families with no angle still show (this is the "not a flat checklist" point):

```tsx
"use client";

import type { ResearchRun } from "@/lib/researchTypes";
import { buildCoverageTree } from "@/lib/researchSelectors";

const STATUS_STYLES: Record<string, string> = {
  active: "border-emerald-700 text-emerald-300",
  blocked_missing_fact: "border-amber-700 text-amber-300",
  out_of_scope: "border-slate-700 text-slate-500",
  discovery_candidate: "border-purple-700 text-purple-300",
};

function statusClass(status: string): string {
  return STATUS_STYLES[status] ?? "border-slate-700 text-slate-300";
}

export function ResearchGraph({ run }: { run: ResearchRun | null }) {
  if (!run) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">
        Research graph will appear after a run.
      </div>
    );
  }

  const tree = buildCoverageTree(run);

  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Coverage graph</h2>
      <ul className="flex flex-col gap-3">
        {tree.map((family) => (
          <li key={family.id} className={`rounded border-l-2 pl-3 ${statusClass(family.status)}`}>
            <div className="text-sm font-semibold">
              {family.family} <span className="text-xs font-normal">({family.status})</span>
            </div>
            <p className="text-xs text-slate-400">{family.reason}</p>
            <ul className="mt-2 flex flex-col gap-2">
              {family.angles.map((angle) => (
                <li key={angle.id} className={`rounded border-l-2 pl-3 ${statusClass(angle.status)}`}>
                  <div className="text-xs font-semibold">{angle.label}</div>
                  <ul className="mt-1 flex flex-col gap-1">
                    {angle.hypotheses.map((hypothesis) => (
                      <li key={hypothesis.id} className="rounded border-l-2 border-slate-700 pl-3">
                        <div className="text-xs text-slate-200">{hypothesis.question}</div>
                        <div className="text-[11px] text-slate-500">
                          {hypothesis.tasks.length} task{hypothesis.tasks.length === 1 ? "" : "s"}:{" "}
                          {hypothesis.tasks.map((task) => task.assigned_agent).join(", ") || "none"}
                        </div>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
              {family.angles.length === 0 && (
                <li className="text-[11px] text-slate-500">No angle pursued for this family.</li>
              )}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 3: Build the trace panel component**

Create `web/src/components/TracePanel.tsx`. It orders events by timestamp, shows the worker count from the scoped graph, and highlights `failed` / `needs_review` rows so the repair moment stands out:

```tsx
"use client";

import type { ResearchRun, TraceEvent } from "@/lib/researchTypes";
import { getWorkerCount } from "@/lib/researchSelectors";

const STATUS_STYLES: Record<TraceEvent["status"], string> = {
  queued: "text-slate-400",
  running: "text-sky-300",
  done: "text-emerald-300",
  failed: "text-red-400",
  needs_review: "text-amber-300",
};

export function TracePanel({ run }: { run: ResearchRun | null }) {
  if (!run) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">
        Trace will stream here after a run.
      </div>
    );
  }

  const events = [...run.trace_events].sort((a, b) => a.ts.localeCompare(b.ts));

  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Swarm trace</h2>
        <span className="rounded bg-slate-800 px-2 py-1 text-xs">
          {getWorkerCount(run)} workers from scoped graph
        </span>
      </div>
      <ol className="flex flex-col gap-2">
        {events.map((event) => {
          const highlight = event.status === "failed" || event.status === "needs_review";
          return (
            <li key={event.id} className={`rounded px-2 py-1 text-xs ${highlight ? "bg-slate-800" : ""}`}>
              <span className={`font-semibold ${STATUS_STYLES[event.status]}`}>
                {event.actor} · {event.phase}
              </span>
              <span className="ml-2 text-slate-300">{event.message}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
```

- [ ] **Step 4: Build the verification summary component**

Create `web/src/components/VerificationSummary.tsx`:

```tsx
"use client";

import type { ResearchRun } from "@/lib/researchTypes";

export function VerificationSummary({ run }: { run: ResearchRun | null }) {
  if (!run) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">
        Verification summary appears after a run.
      </div>
    );
  }

  const verdicts = run.verification_verdicts;
  const passed = verdicts.filter((verdict) => verdict.verdict === "pass").length;
  const needsReview = verdicts.filter((verdict) => verdict.verdict === "needs_review").length;
  const failed = verdicts.filter((verdict) => verdict.verdict === "fail").length;

  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Verification</h2>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-slate-400">Jurisdictions</dt>
        <dd>{run.jurisdiction_stack.join(", ")}</dd>
        <dt className="text-slate-400">Passed</dt>
        <dd className="text-emerald-300">{passed}</dd>
        <dt className="text-slate-400">Needs review</dt>
        <dd className="text-amber-300">{needsReview}</dd>
        <dt className="text-slate-400">Failed</dt>
        <dd className="text-red-400">{failed}</dd>
        <dt className="text-slate-400">Repair tickets</dt>
        <dd>{run.repair_tickets.length}</dd>
      </dl>
    </div>
  );
}
```

- [ ] **Step 5: Build the applicability matrix component**

Create `web/src/components/ApplicabilityMatrix.tsx`. Clicking a row calls `onSelect`; needs-review rows keep a distinct left border so nothing disappears when evidence fails:

```tsx
"use client";

import type { Determination, ResearchRun } from "@/lib/researchTypes";

const APPLIES_STYLES: Record<Determination["applies"], string> = {
  yes: "text-emerald-300",
  no: "text-slate-400",
  needs_review: "text-amber-300",
};

type Props = {
  run: ResearchRun | null;
  selected: Determination | null;
  onSelect: (determination: Determination) => void;
};

export function ApplicabilityMatrix({ run, selected, onSelect }: Props) {
  if (!run) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">
        Applicability matrix appears after a run.
      </div>
    );
  }

  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Applicability matrix</h2>
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="text-xs uppercase text-slate-500">
            <th className="py-2 pr-2">Requirement</th>
            <th className="py-2 pr-2">Applies</th>
            <th className="py-2 pr-2">Trigger</th>
            <th className="py-2 pr-2">Project fact</th>
            <th className="py-2 pr-2">Confidence</th>
            <th className="py-2 pr-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {run.determinations.map((determination) => {
            const isSelected = selected?.requirement === determination.requirement;
            return (
              <tr
                key={determination.requirement}
                onClick={() => onSelect(determination)}
                className={`cursor-pointer border-t border-slate-800 ${
                  isSelected ? "bg-slate-800" : "hover:bg-slate-800/40"
                } ${determination.review_flag ? "border-l-2 border-l-amber-600" : ""}`}
              >
                <td className="py-2 pr-2">{determination.requirement}</td>
                <td className={`py-2 pr-2 font-semibold ${APPLIES_STYLES[determination.applies]}`}>
                  {determination.applies}
                </td>
                <td className="py-2 pr-2 text-slate-300">{determination.trigger}</td>
                <td className="py-2 pr-2 text-slate-300">{determination.project_fact}</td>
                <td className="py-2 pr-2">{Math.round(determination.confidence * 100)}%</td>
                <td className="py-2 pr-2">
                  {determination.verified ? (
                    <span className="text-emerald-300">verified</span>
                  ) : (
                    <span className="text-amber-300">needs review</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">Select a row to open the evidence drawer.</p>
    </div>
  );
}
```

- [ ] **Step 6: Build the evidence drawer component**

Create `web/src/components/EvidenceDrawer.tsx`. It uses `buildEvidenceView` to resolve sources, verifier checks, and repair history by `hypothesis_id`:

```tsx
"use client";

import type { Determination, ResearchRun } from "@/lib/researchTypes";
import { buildEvidenceView } from "@/lib/researchSelectors";

type Props = {
  run: ResearchRun | null;
  determination: Determination | null;
  onClose: () => void;
};

export function EvidenceDrawer({ run, determination, onClose }: Props) {
  if (!run || !determination) return null;

  const view = buildEvidenceView(run, determination);

  return (
    <aside className="fixed inset-y-0 right-0 z-10 w-full max-w-md overflow-y-auto border-l border-slate-800 bg-slate-900 p-4 shadow-xl">
      <div className="mb-3 flex items-start justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Evidence</h2>
        <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-100">
          Close
        </button>
      </div>

      <h3 className="text-base font-semibold">{determination.requirement}</h3>
      <p className="text-sm text-slate-300">
        Applies: {determination.applies} · confidence {Math.round(determination.confidence * 100)}%
      </p>

      <section className="mt-4">
        <h4 className="text-xs font-semibold uppercase text-slate-500">Sources</h4>
        {view.evidence && view.evidence.sources.length > 0 ? (
          view.evidence.sources.map((source) => (
            <div key={source.url} className="mt-2 rounded border border-slate-800 p-2 text-xs">
              <a href={source.url} className="text-sky-300 underline" target="_blank" rel="noreferrer">
                {source.source_name || source.url}
              </a>
              <p className="mt-1 italic text-slate-300">&ldquo;{source.quote}&rdquo;</p>
              <p className="mt-1 text-slate-500">hash: {source.content_hash}</p>
              <p className="text-slate-500">fetched: {source.fetched_at}</p>
              <p className="text-slate-500">effective: {source.effective_date ?? "unknown"}</p>
            </div>
          ))
        ) : (
          <p className="mt-1 text-xs text-slate-500">No source evidence (missing fact or blocked).</p>
        )}
      </section>

      <section className="mt-4">
        <h4 className="text-xs font-semibold uppercase text-slate-500">Verifier checks</h4>
        {view.verdict ? (
          <ul className="mt-2 flex flex-col gap-1 text-xs">
            {Object.entries(view.verdict.checks).map(([name, check]) => (
              <li key={name}>
                <span className={check.pass ? "text-emerald-300" : "text-red-400"}>
                  {check.pass ? "PASS" : "FAIL"}
                </span>{" "}
                <span className="text-slate-300">{name}</span>: {check.reason}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-slate-500">No verdict recorded.</p>
        )}
      </section>

      <section className="mt-4">
        <h4 className="text-xs font-semibold uppercase text-slate-500">Repair history</h4>
        {view.repairs.length > 0 ? (
          view.repairs.map((repair) => (
            <div key={repair.ticket_id} className="mt-2 rounded border border-amber-800 p-2 text-xs">
              <p className="font-semibold text-amber-300">{repair.failure_type}</p>
              <p className="text-slate-300">{repair.observed_problem}</p>
              <p className="text-slate-400">Action: {repair.repair_action}</p>
            </div>
          ))
        ) : (
          <p className="mt-1 text-xs text-slate-500">No repairs needed.</p>
        )}
      </section>
    </aside>
  );
}
```

- [ ] **Step 7: Build the report panel component**

Create `web/src/components/ReportPanel.tsx`:

```tsx
"use client";

import type { ResearchRun } from "@/lib/researchTypes";

export function ReportPanel({ run }: { run: ResearchRun | null }) {
  if (!run) return null;
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">Report</h2>
      <p className="whitespace-pre-wrap text-sm text-slate-300">{run.report_markdown}</p>
    </div>
  );
}
```

- [ ] **Step 8: Wire the page shell to the fixture**

Replace `web/src/app/page.tsx` with the client shell. `Run` loads `demoResearchRun` for now; Task 6 swaps that one line for the API call:

```tsx
"use client";

import { useState } from "react";
import type { Determination, ResearchRun } from "@/lib/researchTypes";
import { demoResearchRun } from "@/lib/demoResearchRun";
import { ProjectInput } from "@/components/ProjectInput";
import { ResearchGraph } from "@/components/ResearchGraph";
import { TracePanel } from "@/components/TracePanel";
import { VerificationSummary } from "@/components/VerificationSummary";
import { ApplicabilityMatrix } from "@/components/ApplicabilityMatrix";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { ReportPanel } from "@/components/ReportPanel";

const SOCAL_DEMO_DESCRIPTION =
  "A Los Angeles County manufacturer is adding a coating booth and storing 60 gallons of a new flammable solvent. NAICS 332813, SIC 3471.";

export default function Home() {
  const [projectDescription, setProjectDescription] = useState("");
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [selected, setSelected] = useState<Determination | null>(null);

  async function handleRun() {
    setIsRunning(true);
    setSelected(null);
    setRun(demoResearchRun);
    setIsRunning(false);
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <section className="mx-auto grid max-w-7xl gap-4 p-4 lg:grid-cols-[320px_minmax(0,1fr)_320px]">
        <ProjectInput
          value={projectDescription}
          onChange={setProjectDescription}
          onLoadDemo={() => setProjectDescription(SOCAL_DEMO_DESCRIPTION)}
          onRun={handleRun}
          isRunning={isRunning}
          runStatus={run?.status ?? "idle"}
        />
        <div className="flex flex-col gap-4">
          <ResearchGraph run={run} />
          <TracePanel run={run} />
        </div>
        <VerificationSummary run={run} />
        <div className="lg:col-span-3">
          <ApplicabilityMatrix run={run} selected={selected} onSelect={setSelected} />
        </div>
        <div className="lg:col-span-3">
          <ReportPanel run={run} />
        </div>
      </section>
      <EvidenceDrawer run={run} determination={selected} onClose={() => setSelected(null)} />
    </main>
  );
}
```

- [ ] **Step 9: Verify the full surface renders from the fixture**

Run:

```bash
cd web
npm run dev
```

Expected: load the demo, click Run, and see the coverage graph, trace with worker count, verification summary, matrix, report, and (on row click) the evidence drawer — all with no backend.

- [ ] **Step 10: Commit**

```bash
git add web/src/app/page.tsx web/src/components
git commit -m "feat: render Person B product surface from fixture"
```

### Task 6: Swap Fixture Data To API Data

**Files:**
- Create: `web/src/lib/runResearch.ts`
- Modify: `web/src/app/page.tsx`

- [ ] **Step 1: Add the API client with fixture fallback**

Create `web/src/lib/runResearch.ts`. If the endpoint is missing or errors, it falls back to `demoResearchRun` so the demo never dead-ends:

```ts
import type { ResearchRun } from "./researchTypes";
import { demoResearchRun } from "./demoResearchRun";

export type RunResult = { run: ResearchRun; usedFallback: boolean };

export async function runResearch(projectDescription: string): Promise<RunResult> {
  try {
    const response = await fetch("/api/research/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_description: projectDescription, demo_documents: [] }),
    });

    const payload = (await response.json()) as ResearchRun | { error: string; run?: ResearchRun };

    if (!response.ok) {
      if ("run" in payload && payload.run) return { run: payload.run, usedFallback: false };
      throw new Error("error" in payload ? payload.error : "Research run failed");
    }

    return { run: payload as ResearchRun, usedFallback: false };
  } catch {
    return { run: demoResearchRun, usedFallback: true };
  }
}
```

- [ ] **Step 2: Call the API client from the page**

In `web/src/app/page.tsx`, add a fallback flag and replace the body of `handleRun`. Add near the other state hooks:

```tsx
const [usedFallback, setUsedFallback] = useState(false);
```

Replace the `handleRun` function with:

```tsx
async function handleRun() {
  setIsRunning(true);
  setSelected(null);
  const result = await runResearch(projectDescription);
  setRun(result.run);
  setUsedFallback(result.usedFallback);
  setIsRunning(false);
}
```

Add the import at the top:

```tsx
import { runResearch } from "@/lib/runResearch";
```

And render a badge when the fallback fired, just inside `<section>` above `ProjectInput`:

```tsx
{usedFallback && (
  <p className="rounded bg-amber-900/50 px-3 py-2 text-xs text-amber-200 lg:col-span-3">
    Live API unavailable — showing cached demo run.
  </p>
)}
```

- [ ] **Step 3: Verify fallback works without a backend**

Run:

```bash
cd web
npm run dev
```

Expected: with no `/api/research/run` route, clicking Run shows the cached demo run and the amber fallback badge. The full surface still renders.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/runResearch.ts web/src/app/page.tsx
git commit -m "feat: call research API with cached fixture fallback"
```

### Task 7: B-Lane Smoke Tests

**Files:**
- Run: `web/src/lib/researchSelectors.test.ts` (created in Task 4)
- Document manual QA in `web/README.md` if anything needs a note.

- [ ] **Step 1: Run the automated selector tests**

Run:

```bash
cd web
npx vitest run
```

Expected: all selector tests from Task 4 pass.

- [ ] **Step 2: Test the seeded happy path manually**

Run:

```bash
cd web
npm run dev
```

Manual checks:

- load sample scenario,
- run fixture,
- verify worker count appears,
- verify HMBP failure appears,
- verify repair ticket appears,
- verify matrix renders,
- open evidence drawer,
- confirm quote, URL, hash, and verifier checks are visible.

Expected: the full flow works in under 3 minutes.

- [ ] **Step 3: Test partial data behavior**

Temporarily set `demoResearchRun.status = "partial"` and remove one `evidence_bundles` entry.

Expected:

- graph still renders,
- trace still renders,
- matrix still renders needs-review rows,
- no spinner-only dead end appears.

### Task 8: Demo Script

**Files:**
- Create: `web/DEMO_SCRIPT.md`

- [ ] **Step 1: Add the three-minute script**

Create `web/DEMO_SCRIPT.md`:

```markdown
# Three-Minute Demo Script

1. Load the SoCal manufacturing demo.
2. Say: "This facility is adding a coating booth and storing a new hazardous liquid."
3. Show the coverage floor: air, stormwater, hazmat, waste, wastewater.
4. Show expansion from coverage families into regulatory angles, hypotheses, and source tasks.
5. Point to worker count: "The worker count comes from the scoped graph, not a fixed agent team."
6. Pause on verifier failure: "The quote mentions thresholds, but the extracted claim said all storage."
7. Show repair ticket: "The orchestrator reruns only the failed threshold extraction."
8. Open the final matrix.
9. Open the HMBP evidence drawer and show quote, URL, hash, fetched date, and checks.
10. Close: "This is not a chatbot answer. It is a source-backed matrix that proves what it can and fails closed where it cannot."
```

- [ ] **Step 2: Rehearse the repair moment**

Run the demo twice and time the flow.

Expected: verifier failure plus repair explanation lands in under 20 seconds.

## Self-Review

Spec coverage:

- B1 app shell: Task 1 and Task 5.
- B2 sample scenario UX: Task 5 (Step 1, Step 8).
- B3 graph visualization (`CoverageFamily -> RegulatoryAngle -> ResearchHypothesis -> ResearchTask`): Task 4 selector + Task 5 Step 2.
- B4 trace panel and dynamic worker count: Task 4 `getWorkerCount` + Task 5 Step 3.
- B5 jurisdiction and verification summary: Task 5 Step 4.
- B6 matrix: Task 5 Step 5.
- B7 evidence drawer: Task 4 `buildEvidenceView` + Task 5 Step 6.
- B8 report/export: Task 5 Step 7 covers report view; export can be added after the core demo works.
- B9 run states and failure UX: Task 6 (fallback badge) and Task 7 (partial-data check).
- B10 demo script: Task 8.

Placeholder scan:

- Every code step now contains the actual file content (selectors, all seven components, page shell, API client). No "implement later" or behavior-only steps remain.
- The only deliberate coordination items are listed as contract questions for Person A.

Type consistency:

- `hypothesis_id` is optional on `Determination` because the remote contract does not require it yet. `buildEvidenceView` handles the undefined case (verified by a test in Task 4) and the fixture supplies `hypothesis_id` so the drawer stays stable.
- Selector node types (`GraphFamilyNode`, `GraphAngleNode`, `GraphHypothesisNode`) extend the base artifact types from Task 2, so the graph component consumes exactly the shapes the fixture produces.
- Function names are consistent across tasks: `buildCoverageTree`, `getWorkerCount`, and `buildEvidenceView` are defined in Task 4 and imported unchanged in Tasks 5 and 6.
