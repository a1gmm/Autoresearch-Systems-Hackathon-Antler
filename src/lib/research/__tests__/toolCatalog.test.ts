import { describe, expect, it } from "vitest";
import { seededComplexScope } from "../fixtures/scenarios";
import { planResearch } from "../planner";
import {
  blockedToolIdsForRole,
  getTool,
  harnessToolCatalog,
  isToolScopedToRole,
  researchWorkerToolIds,
  sdsReviewerToolIds,
  subagentControlToolIds,
  toolIdsForRole,
  universalHarnessToolIds
} from "../toolCatalog";

describe("harness tool catalog", () => {
  it("keeps tool ids unique", () => {
    const ids = harnessToolCatalog.map((tool) => tool.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("includes the universal harness and subagent control primitives", () => {
    expect(universalHarnessToolIds).toEqual(
      expect.arrayContaining([
        "log_step",
        "emit_trace_event",
        "validate_artifact_schema",
        "send_message",
        "escalate_to_human"
      ])
    );
    expect(subagentControlToolIds).toEqual(
      expect.arrayContaining([
        "spawn_subagents",
        "send_subagent_message",
        "wait_for_subagents",
        "cancel_subagent"
      ])
    );
  });

  it("scopes researcher workers to safe retrieval tools plus universal harness tools", () => {
    const researcherTools = toolIdsForRole("researcher");
    const workerTools = researchWorkerToolIds();

    expect(workerTools).toEqual(
      expect.arrayContaining([
        "get_source_pointers",
        "fetch_source",
        "prove_currency",
        "extract_threshold",
        "evaluate_predicate",
        "quarantine_injection",
        "log_step",
        "send_message"
      ])
    );
    expect(workerTools.every((toolId) => researcherTools.includes(toolId))).toBe(true);
    expect(workerTools).not.toContain("get_form");
    expect(workerTools).not.toContain("build_applicability_matrix");
  });

  it("scopes SDS reviewers to SDS artifact tools plus universal harness tools", () => {
    const sdsReviewerTools = toolIdsForRole("sds_reviewer");
    const allowedTools = sdsReviewerToolIds();
    const blockedTools = blockedToolIdsForRole("sds_reviewer");

    expect(allowedTools).toEqual(
      expect.arrayContaining([
        "parse_sds_text",
        "map_sds_sections",
        "validate_sds_section_completeness",
        "extract_sds_hazard_fields",
        "extract_sds_storage_fields",
        "extract_sds_disposal_transport_fields",
        "flag_sds_inconsistencies",
        "emit_permit_handoff_facts",
        "log_step",
        "validate_artifact_schema"
      ])
    );
    expect(allowedTools.every((toolId) => sdsReviewerTools.includes(toolId))).toBe(true);
    expect(blockedTools).toEqual(
      expect.arrayContaining(["build_applicability_matrix", "verify_determination", "freshness_sweep"])
    );
    expect(allowedTools).not.toContain("build_applicability_matrix");
    expect(isToolScopedToRole("emit_permit_handoff_facts", "researcher")).toBe(false);
  });

  it("limits SDS reviewer tools to SDS artifact and audit-safe write targets", () => {
    const allowedWrites = new Set(["none", "audit_log", "sds_documents", "sds_reviews", "permit_handoff_facts"]);

    for (const toolId of sdsReviewerToolIds()) {
      expect(allowedWrites.has(getTool(toolId).writes)).toBe(true);
    }
  });

  it("rejects tools outside a role scope", () => {
    expect(isToolScopedToRole("fetch_source", "researcher")).toBe(true);
    expect(isToolScopedToRole("fetch_source", "synthesizer")).toBe(false);
    expect(isToolScopedToRole("send_message", "synthesizer")).toBe(true);
    expect(isToolScopedToRole("spawn_subagents", "researcher")).toBe(false);
  });

  it("separates claim, set, and process verification tools", () => {
    const verifierTools = toolIdsForRole("verifier");

    expect(verifierTools).toEqual(
      expect.arrayContaining([
        "verify_determination",
        "self_consistency",
        "verify_determination_set",
        "verify_process_trace",
        "run_eval_set"
      ])
    );
    expect(isToolScopedToRole("verify_determination_set", "researcher")).toBe(false);
    expect(isToolScopedToRole("verify_process_trace", "system")).toBe(true);
  });

  it("plans research tasks with cataloged tool ids", () => {
    const catalogIds = new Set(harnessToolCatalog.map((tool) => tool.id));
    const plan = planResearch(seededComplexScope("run_tools", "demo"));

    expect(plan.research_tasks.length).toBeGreaterThanOrEqual(5);
    for (const task of plan.research_tasks) {
      expect(task.allowed_tools.length).toBeGreaterThan(0);
      expect(task.allowed_tools.every((toolId) => catalogIds.has(toolId))).toBe(true);
      expect(task.allowed_tools).toEqual(expect.arrayContaining(universalHarnessToolIds));
      expect(task.blocked_tools.every((toolId) => catalogIds.has(toolId))).toBe(true);
      expect(task.blocked_tools).toContain("get_form");
    }
  });
});
