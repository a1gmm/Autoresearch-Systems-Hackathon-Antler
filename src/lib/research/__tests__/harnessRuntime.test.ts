import { describe, expect, it } from "vitest";
import { createHarnessContext, type HarnessCall, HarnessToolScopeError } from "../harness";
import { type AgentRole, type HarnessToolId, sdsReviewerToolIds } from "../toolCatalog";

describe("harness runtime scope", () => {
  it("allows SDS reviewer tools and records calls in order", () => {
    const harness = createHarnessContext({
      role: "sds_reviewer",
      allowed_tools: sdsReviewerToolIds(),
      blocked_tools: []
    });

    harness.callTool("map_sds_sections");
    harness.callTool("emit_permit_handoff_facts");

    expect(harness.calls.map((call) => call.tool_id)).toEqual([
      "map_sds_sections",
      "emit_permit_handoff_facts"
    ]);
    expect(harness.calls[0]?.ts).toEqual(expect.any(String));
    expect(new Date(harness.calls[0]?.ts ?? Number.NaN).toString()).not.toBe("Invalid Date");
  });

  it("rejects blocked final permit, memory, and system tools for SDS reviewers", () => {
    const harness = createHarnessContext({
      role: "sds_reviewer",
      allowed_tools: sdsReviewerToolIds(),
      blocked_tools: ["build_applicability_matrix", "verify_determination", "freshness_sweep"]
    });

    expect(() => harness.callTool("build_applicability_matrix")).toThrow(HarnessToolScopeError);
    expect(() => harness.callTool("verify_determination")).toThrow(HarnessToolScopeError);
    expect(() => harness.callTool("freshness_sweep")).toThrow(HarnessToolScopeError);
    expect(harness.calls).toEqual([]);
  });

  it("rejects tools that were not granted even when they are not blocked", () => {
    const harness = createHarnessContext({
      role: "sds_reviewer",
      allowed_tools: ["map_sds_sections"],
      blocked_tools: []
    });

    expect(() => harness.callTool("emit_permit_handoff_facts")).toThrow(HarnessToolScopeError);
    expect(harness.calls).toEqual([]);
  });

  it("does not let returned tool snapshots mutate enforcement", () => {
    const grantHarness = createHarnessContext({
      role: "sds_reviewer",
      allowed_tools: ["map_sds_sections"],
      blocked_tools: []
    });

    tryMutateTools(grantHarness.allowed_tools, "emit_permit_handoff_facts");

    expect(() => grantHarness.callTool("emit_permit_handoff_facts")).toThrow(HarnessToolScopeError);
    expect(grantHarness.calls).toEqual([]);

    const blockHarness = createHarnessContext({
      role: "sds_reviewer",
      allowed_tools: ["map_sds_sections"],
      blocked_tools: []
    });

    tryMutateTools(blockHarness.blocked_tools, "map_sds_sections");

    expect(() => blockHarness.callTool("map_sds_sections")).not.toThrow();
    expect(blockHarness.calls.map((call) => call.tool_id)).toEqual(["map_sds_sections"]);
  });

  it("rejects granted tools outside the SDS reviewer role scope", () => {
    const harness = createHarnessContext({
      role: "sds_reviewer",
      allowed_tools: ["build_applicability_matrix"],
      blocked_tools: []
    });

    expect(() => harness.callTool("build_applicability_matrix")).toThrow(HarnessToolScopeError);
    expect(harness.calls).toEqual([]);
  });

  it("does not let input role mutation alter enforcement", () => {
    const input: {
      role: AgentRole;
      allowed_tools: HarnessToolId[];
      blocked_tools: HarnessToolId[];
    } = {
      role: "sds_reviewer",
      allowed_tools: ["build_applicability_matrix"],
      blocked_tools: []
    };
    const harness = createHarnessContext(input);

    input.role = "synthesizer";

    expect(harness.role).toBe("sds_reviewer");
    expect(() => harness.callTool("build_applicability_matrix")).toThrow(HarnessToolScopeError);
    expect(harness.calls).toEqual([]);
  });

  it("does not let calls snapshots erase or forge the audit log", () => {
    const harness = createHarnessContext({
      role: "sds_reviewer",
      allowed_tools: ["map_sds_sections"],
      blocked_tools: []
    });

    harness.callTool("map_sds_sections");
    tryEraseCalls(harness.calls);

    expect(harness.calls.map((call) => call.tool_id)).toEqual(["map_sds_sections"]);

    tryForgeCall(harness.calls, {
      tool_id: "emit_permit_handoff_facts",
      ts: "2026-05-31T00:00:00.000Z"
    });

    expect(harness.calls.map((call) => call.tool_id)).toEqual(["map_sds_sections"]);
  });
});

function tryMutateTools(tools: readonly HarnessToolId[], toolId: HarnessToolId) {
  try {
    (tools as HarnessToolId[]).push(toolId);
  } catch {
    // Frozen snapshots are acceptable; the assertion is that enforcement is unchanged.
  }
}

function tryEraseCalls(calls: readonly HarnessCall[]) {
  try {
    (calls as HarnessCall[]).splice(0, calls.length);
  } catch {
    // Frozen snapshots are acceptable; the assertion is that enforcement is unchanged.
  }
}

function tryForgeCall(calls: readonly HarnessCall[], call: HarnessCall) {
  try {
    (calls as HarnessCall[]).push(call);
  } catch {
    // Frozen snapshots are acceptable; the assertion is that enforcement is unchanged.
  }
}
