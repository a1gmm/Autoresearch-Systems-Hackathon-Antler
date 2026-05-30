import { describe, expect, it } from "vitest";
import { runResearch } from "./research/run";
import {
  buildCoverageTree,
  buildEvidenceView,
  getWorkerCount,
  hypothesisIdForDeterminationIndex,
} from "./researchSelectors";

const SOCAL =
  "A Los Angeles County manufacturer is adding a coating booth and storing 60 gallons of a new flammable solvent.";

describe("research selectors against the live engine", () => {
  it("buildCoverageTree returns one node per coverage family and nests angle -> hypothesis -> task correctly", async () => {
    const run = await runResearch({ project_description: SOCAL, demo_documents: [] });
    const tree = buildCoverageTree(run);

    expect(tree).toHaveLength(run.coverage_family_statuses.length);
    expect(tree.length).toBeGreaterThan(0);

    for (const family of tree) {
      for (const angle of family.angles) {
        expect(angle.family).toBe(family.family);
        for (const hypothesis of angle.hypotheses) {
          expect(hypothesis.angle_id).toBe(angle.id);
        }
      }
    }
  });

  it("getWorkerCount derives from the scoped task graph, not a fixed team", async () => {
    const run = await runResearch({ project_description: SOCAL, demo_documents: [] });
    expect(getWorkerCount(run)).toBe(run.research_tasks.length);
  });

  it("aligns each determination with its hypothesis by index (the drawer join)", async () => {
    const run = await runResearch({ project_description: SOCAL, demo_documents: [] });

    expect(run.determinations).toHaveLength(run.research_graph.length);

    const hypothesisId = hypothesisIdForDeterminationIndex(run, 0);
    expect(hypothesisId).toBe(run.research_graph[0].id);

    const view = buildEvidenceView(run, hypothesisId);
    expect(view.hypothesisId).toBe(hypothesisId);
    expect(Array.isArray(view.repairs)).toBe(true);
  });
});
