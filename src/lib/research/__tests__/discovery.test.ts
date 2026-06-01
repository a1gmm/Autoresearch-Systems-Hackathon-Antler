import { describe, it, expect } from "vitest";
import { stageNovelRegime } from "../discovery";

describe("discovery staging (propose_map_entry)", () => {
  it("stages an un-registried regime as unverified + needs_review", () => {
    const staged = stageNovelRegime("fire_code", "Spray booth may trigger fire-code permit");
    expect(staged.human_verified).toBe(false);
    expect(staged.status).toBe("needs_review");
    expect(staged.family).toBe("fire_code");
    expect(staged.rationale).toMatch(/spray booth/i);
    expect(staged.id).toMatch(/^staged-/);
  });

  it("never asserts applicability — always needs_review", () => {
    const staged = stageNovelRegime("novel-regime-x", "reasoned hunch");
    expect(staged.status).toBe("needs_review");
  });
});
