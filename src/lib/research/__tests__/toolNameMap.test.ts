import { describe, expect, it } from "vitest";
import { researcherCoreToolIds } from "../toolCatalog";
import { SDK_TOOL_FOR_HARNESS, researcherSdkAllowedTools, sdkToolName } from "../toolNameMap";

describe("toolNameMap", () => {
  it("maps every researcher core tool to a non-empty string or explicit null (never undefined)", () => {
    for (const id of researcherCoreToolIds) {
      expect(id in SDK_TOOL_FOR_HARNESS).toBe(true);
      const mapped = SDK_TOOL_FOR_HARNESS[id];
      expect(mapped).not.toBeUndefined();
      if (mapped !== null) {
        expect(typeof mapped).toBe("string");
        expect(mapped.length).toBeGreaterThan(0);
      }
    }
  });

  it("maps fetch_source to the WebFetch SDK built-in", () => {
    expect(SDK_TOOL_FOR_HARNESS.fetch_source).toBe("WebFetch");
    expect(sdkToolName("fetch_source")).toBe("WebFetch");
  });

  it("maps read_skill to null (custom/policy, not an SDK built-in)", () => {
    expect(SDK_TOOL_FOR_HARNESS.read_skill).toBeNull();
    expect(sdkToolName("read_skill")).toBeNull();
  });

  it("grants the live researcher both WebFetch and WebSearch", () => {
    const allowed = researcherSdkAllowedTools();
    expect(allowed).toContain("WebFetch");
    expect(allowed).toContain("WebSearch");
  });
});
