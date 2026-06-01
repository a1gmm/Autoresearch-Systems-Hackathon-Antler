import { describe, it, expect } from "vitest";
import { availableSkillIds, readSkill } from "../skillReader";

describe("skillReader (TS read_skill)", () => {
  it("lists the on-disk family skill ids", () => {
    const ids = availableSkillIds();
    expect(ids).toContain("ca-hmbp");
    expect(ids).toContain("scaqmd-air");
  });

  it("reads a skill's SKILL.md text", () => {
    expect(readSkill("ca-hmbp")).toMatch(/HMBP/i);
  });

  it("throws on an unknown skill id", () => {
    expect(() => readSkill("does-not-exist")).toThrow(/unknown skill/i);
  });
});
