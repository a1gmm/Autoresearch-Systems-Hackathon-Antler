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
