import { afterEach, describe, expect, it } from "vitest";
import { getResearchMode, isFixtureMode } from "../config";
import { runLocalResearchPool } from "../workers";
import { __setFetchForTests } from "../modal/researchPool";
import type { ResearchHypothesis, ResearchTask } from "../types";

const hypothesis: ResearchHypothesis = {
  id: "H-AIR-201",
  angle_id: "A-AIR-EMITTING-EQUIPMENT",
  family: "air",
  question: "Does the new equipment require a permit?",
  required_facts: [],
  expected_source_type: "regulation",
  success_criteria: [],
  dependencies: [],
};
const task: ResearchTask = {
  task_id: "T-AIR-201",
  hypothesis_id: "H-AIR-201",
  assigned_agent: "air_researcher",
  allowed_tools: [],
  blocked_tools: [],
  budget: { max_sources: 3, max_runtime_seconds: 30, max_model_calls: 4 },
};

const ENV_KEYS = ["RESEARCH_MODE", "MODAL_RESEARCH_ENDPOINT", "MODAL_RESEARCH_TOKEN", "USE_MODAL"] as const;
const saved: Record<string, string | undefined> = {};
for (const k of ENV_KEYS) saved[k] = process.env[k];

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (saved[k] === undefined) delete process.env[k];
    else process.env[k] = saved[k];
  }
  __setFetchForTests(null);
});

describe("research mode — production defaults to live, never silently fakes", () => {
  it("defaults to live mode in production (no RESEARCH_MODE set)", () => {
    delete process.env.RESEARCH_MODE;
    delete process.env.USE_MODAL;
    expect(getResearchMode()).toBe("live");
    expect(isFixtureMode()).toBe(false);
  });

  it("uses fixtures only when explicitly opted in", () => {
    process.env.RESEARCH_MODE = "fixture";
    expect(getResearchMode()).toBe("fixture");
    expect(isFixtureMode()).toBe(true);
  });

  it("live mode with an unreachable backend FAILS CLOSED (needs_review), never canned fixtures", async () => {
    process.env.RESEARCH_MODE = "live";
    process.env.MODAL_RESEARCH_ENDPOINT = "https://modal.example/run";
    process.env.MODAL_RESEARCH_TOKEN = "tok";
    __setFetchForTests(async () => {
      throw new Error("network down");
    });

    const result = await runLocalResearchPool([task], [hypothesis]);

    // Fail closed: no fabricated "applies", no fixture quote, every bundle needs_review.
    expect(result.degraded).toBeTruthy();
    for (const bundle of result.bundles) {
      expect(bundle.researcher_conclusion).toBe("needs_review");
      expect(bundle.sources).toEqual([]);
    }
  });

  it("live mode without endpoint configured FAILS CLOSED, does not fall back to fixtures", async () => {
    process.env.RESEARCH_MODE = "live";
    delete process.env.MODAL_RESEARCH_ENDPOINT;
    delete process.env.MODAL_RESEARCH_TOKEN;

    const result = await runLocalResearchPool([task], [hypothesis]);

    expect(result.degraded).toBeTruthy();
    for (const bundle of result.bundles) {
      expect(bundle.researcher_conclusion).toBe("needs_review");
      expect(bundle.sources).toEqual([]);
    }
  });
});
