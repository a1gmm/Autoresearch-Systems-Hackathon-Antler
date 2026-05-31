import { afterEach, describe, expect, it } from "vitest";
import { runLocalResearchPool } from "../workers";
import { __setSpawnForTests } from "../modal/runModalPool";
import type { ResearchHypothesis, ResearchTask } from "../types";

const hypothesis: ResearchHypothesis = {
  id: "H-AIR-201",
  angle_id: "A-AIR-EMITTING-EQUIPMENT",
  family: "air",
  question: "Does SCAQMD Rule 201 require a permit?",
  required_facts: [],
  expected_source_type: "regulation",
  success_criteria: [],
  dependencies: [],
};

const task: ResearchTask = {
  task_id: "T-1",
  hypothesis_id: "H-AIR-201",
  assigned_agent: "air_researcher",
  allowed_tools: [],
  blocked_tools: [],
  budget: { max_sources: 3, max_runtime_seconds: 30, max_model_calls: 4 },
};

const ORIGINAL_MODE = process.env.RESEARCH_MODE;

afterEach(() => {
  if (ORIGINAL_MODE === undefined) delete process.env.RESEARCH_MODE;
  else process.env.RESEARCH_MODE = ORIGINAL_MODE;
  __setSpawnForTests(null);
});

describe("runLocalResearchPool routing", () => {
  it("uses the fixture path in fixture mode (no modal spawn)", async () => {
    delete process.env.RESEARCH_MODE; // default fixture
    let spawned = false;
    __setSpawnForTests(() => {
      spawned = true;
      throw new Error("spawn should not be called in fixture mode");
    });

    const [bundle] = await runLocalResearchPool([task], [hypothesis]);

    expect(spawned).toBe(false);
    expect(bundle.sources[0]?.source_name).toBe("SCAQMD Rule 201");
  });

  it("routes to the modal pool in live_modal mode", async () => {
    process.env.RESEARCH_MODE = "live_modal";
    let spawned = false;
    // Fake child process that emits a valid bundle line then closes 0.
    __setSpawnForTests(() => {
      spawned = true;
      const handlers: Record<string, (...a: unknown[]) => void> = {};
      const stdout = { on: (e: string, cb: (...a: unknown[]) => void) => { handlers[`out:${e}`] = cb; } };
      const stderr = { on: () => {} };
      queueMicrotask(() => {
        handlers["out:data"]?.(
          Buffer.from('PERMITPILOT_BUNDLE_JSON {"hypothesis_id":"H-AIR-201","sources":[],"extracted_claims":[],"researcher_conclusion":"applies","uncertainties":[]}\n')
        );
        handlers["close"]?.(0, null);
      });
      return {
        stdout,
        stderr,
        kill: () => {},
        on: (e: string, cb: (...a: unknown[]) => void) => { handlers[e] = cb; },
      } as never;
    });

    const [bundle] = await runLocalResearchPool([task], [hypothesis]);

    expect(spawned).toBe(true);
    expect(bundle.hypothesis_id).toBe("H-AIR-201");
  });
});
