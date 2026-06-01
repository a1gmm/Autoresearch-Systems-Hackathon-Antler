import { describe, it, expect } from "vitest";
import { openAiOrchestratorLlmFn } from "../orchestrator";

describe("orchestrator LLM seam", () => {
  it("the default impl is offline-safe: no API key -> empty proposal turn", async () => {
    const prev = process.env.OPENAI_API_KEY;
    delete process.env.OPENAI_API_KEY;
    try {
      const out = await openAiOrchestratorLlmFn([{ role: "user", content: "hi" }], []);
      expect(out.tool_calls).toEqual([]);
      expect(out.content).toBeNull();
    } finally {
      if (prev !== undefined) process.env.OPENAI_API_KEY = prev;
    }
  });
});
