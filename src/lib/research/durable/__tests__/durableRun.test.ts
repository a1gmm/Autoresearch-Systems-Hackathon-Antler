import { describe, it, expect, vi } from "vitest";
import { enqueueRun, getDurableRun, startModalRun, type DurableDeps } from "../durableRun";

function deps(overrides: Partial<DurableDeps> = {}): DurableDeps {
  const runs: Record<string, any> = {};
  const evidence: Record<string, any[]> = {};
  const finalStatus = (overrides as { _finalStatus?: string })._finalStatus;
  return {
    planRun: async (_input: unknown) => ({ run_id: "run_x", scope_pack: { facility: { jurisdiction_stack: ["SCAQMD"] } } as any, plan: { research_tasks: [{ task_id: "T1", hypothesis_id: "H-AIR-201", allowed_tools: [], blocked_tools: [], budget: {} }], research_graph: [{ id: "H-AIR-201", question: "q" }], coverage_family_statuses: [], regulatory_angles: [] } as any, trace_events: [] }),
    finalizeRun: (run_id: string, _scope, _plan, finalEvidence, baseTrace) => {
      const runtimeVerdict = finalEvidence[0]?.bundle?.runtime_review?.verdict ?? finalEvidence[0]?.runtime_review?.verdict;
      return { run_id, status: finalStatus ?? (runtimeVerdict === "needs_review" ? "needs_review" : "done"), determinations: [{ verified: true }], report_markdown: "md", trace_events: baseTrace } as any;
    },
    startModalRun: vi.fn(async () => {}),
    store: {
      createRun: async (r: { run_id: string; [k: string]: unknown }) => { runs[r.run_id] = { ...r }; },
      getRun: async (id: string) => runs[id] ?? null,
      listEvidence: async (id: string) => evidence[id] ?? [],
      updateStatus: async (id: string, s: string) => { runs[id].status = s; },
      finalizeRun: async (id: string, res: Record<string, unknown>) => { Object.assign(runs[id], { status: "done", ...res }); },
    } as any,
    _runs: runs, _evidence: evidence,
    ...overrides,
  } as any;
}

describe("durableRun", () => {
  it("enqueueRun plans, creates a queued run, asks Modal to spawn, returns run_id", async () => {
    const d = deps();
    const res = await enqueueRun({ project_description: "x" }, d);
    expect(res).toEqual({ run_id: "run_x", status: "queued" });
    expect((d as any)._runs["run_x"].status).toBe("queued");
    expect((d as any)._runs["run_x"].task_count).toBe(1);
    expect(d.startModalRun).toHaveBeenCalledOnce();
  });

  it("forwards a task's jurisdiction_context into the Modal task_spec", async () => {
    const spawn = vi.fn(async () => {});
    const d = deps({
      planRun: (async () => ({
        run_id: "run_j", scope_pack: { facility: { jurisdiction_stack: ["South Coast AQMD"] } },
        plan: {
          research_tasks: [{ task_id: "T1", hypothesis_id: "H-AIR-201", allowed_tools: [], blocked_tools: [], budget: {}, jurisdiction_context: "Resolved: South Coast AQMD" }],
          research_graph: [{ id: "H-AIR-201", question: "q" }], coverage_family_statuses: [], regulatory_angles: [],
        }, sds_reviews: [], trace_events: [],
      })) as any,
      startModalRun: spawn,
    });
    await enqueueRun({ project_description: "x" }, d);
    const specs = (spawn.mock.calls[0] as any[])[1] as any[];
    expect(specs[0].jurisdiction_context).toBe("Resolved: South Coast AQMD");
    expect(specs[0].family).toBe("air");
    expect(specs[0].skill_id).toBe("scaqmd-permit-to-construct");
    expect(specs[0].allowed_domains).toContain("www.aqmd.gov");
  });

  it("enqueueRun marks the run failed if Modal spawn throws", async () => {
    const d = deps({ startModalRun: vi.fn(async () => { throw new Error("boom"); }) });
    await expect(enqueueRun({ project_description: "x" }, d)).rejects.toThrow(/boom/);
    expect((d as any)._runs["run_x"].status).toBe("failed");
  });

  it("getDurableRun returns partial while incomplete", async () => {
    const d = deps();
    await enqueueRun({ project_description: "x" }, d);
    Object.assign((d as any)._runs["run_x"], {
      workspace_prefix: "workspace/run_x",
      artifact_index: [{ kind: "draft", path: "workspace/run_x/T1/draft.md", task_id: "T1", hypothesis_id: "H-AIR-201" }],
    });
    const got = await getDurableRun("run_x", d);
    expect(got.status).toBe("queued");
    expect((got as any).workspace_prefix).toBe("workspace/run_x");
    expect((got as any).artifact_index).toEqual([{ kind: "draft", path: "workspace/run_x/T1/draft.md", task_id: "T1", hypothesis_id: "H-AIR-201" }]);
    expect((got as any).determinations).toBeUndefined();
  });

  it("getDurableRun returns failed partial instead of finalizing incomplete failed runs", async () => {
    const d = deps();
    await enqueueRun({ project_description: "x" }, d);
    (d as any)._runs["run_x"].status = "failed";
    const got = await getDurableRun("run_x", d);
    expect(got.status).toBe("failed");
    expect((got as any).determinations).toBeUndefined();
  });

  it("getDurableRun does not finalize failed runs even when all evidence rows are present", async () => {
    const d = deps();
    await enqueueRun({ project_description: "x" }, d);
    (d as any)._runs["run_x"].status = "failed";
    (d as any)._evidence["run_x"] = [{ hypothesis_id: "H-AIR-201", bundle: { hypothesis_id: "H-AIR-201" } }];
    const got = await getDurableRun("run_x", d);
    expect(got.status).toBe("failed");
    expect((got as any).determinations).toBeUndefined();
  });

  it("getDurableRun finalizes once all bundles are present", async () => {
    const d = deps();
    await enqueueRun({ project_description: "x" }, d);
    Object.assign((d as any)._runs["run_x"], {
      trace_events: [{ id: "runtime-1", actor: "reviewer", phase: "review.accepted", status: "done", message: "accepted", ts: "2026-01-01T00:00:00.000Z", run_id: "run_x" }],
      workspace_prefix: "workspace/run_x",
      artifact_index: [{ kind: "review", path: "workspace/run_x/T1/review.json", task_id: "T1", hypothesis_id: "H-AIR-201" }],
    });
    (d as any)._evidence["run_x"] = [{ hypothesis_id: "H-AIR-201", bundle: { hypothesis_id: "H-AIR-201" } }];
    const got = await getDurableRun("run_x", d);
    expect(got.status).toBe("done");
    expect((got as any).determinations).toHaveLength(1);
    expect((got as any).trace_events).toEqual((d as any)._runs["run_x"].trace_events);
    expect((got as any).workspace_prefix).toBe("workspace/run_x");
    expect((got as any).artifact_index).toEqual([{ kind: "review", path: "workspace/run_x/T1/review.json", task_id: "T1", hypothesis_id: "H-AIR-201" }]);
  });

  it("persists computed needs_review status during durable finalization", async () => {
    const d = deps({ _finalStatus: "needs_review" } as any);
    await enqueueRun({ project_description: "x" }, d);
    (d as any)._evidence["run_x"] = [{ hypothesis_id: "H-AIR-201", bundle: { hypothesis_id: "H-AIR-201" } }];
    const got = await getDurableRun("run_x", d);
    expect(got.status).toBe("needs_review");
    expect((d as any)._runs["run_x"].status).toBe("needs_review");
  });

  it("uses runtime reviewer verdicts as durable finalization authority", async () => {
    const d = deps();
    await enqueueRun({ project_description: "x" }, d);
    (d as any)._evidence["run_x"] = [{
      hypothesis_id: "H-AIR-201",
      bundle: {
        hypothesis_id: "H-AIR-201",
        sources: [],
        extracted_claims: [],
        researcher_conclusion: "needs_review",
        uncertainties: ["Reviewer escalated."],
        runtime_review: {
          decision: "needs_human_review",
          verdict: "needs_review",
          artifact_path: "reviews/T1/review.json",
          reason: "Reviewer escalated.",
        },
      },
    }];
    const got = await getDurableRun("run_x", d);
    expect(got.status).toBe("needs_review");
    expect((d as any)._runs["run_x"].status).toBe("needs_review");
  });

  it("getDurableRun 404s on unknown id", async () => {
    const d = deps();
    await expect(getDurableRun("nope", d)).rejects.toThrow(/not found/i);
  });

  it("startModalRun treats JSON error bodies as spawn failures", async () => {
    process.env.MODAL_START_RUN_ENDPOINT = "https://modal.example/start";
    process.env.MODAL_RESEARCH_TOKEN = "token";
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      text: async () => JSON.stringify({ error: "unauthorized" }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(startModalRun("run_x", [])).rejects.toThrow(/unauthorized/);

    vi.unstubAllGlobals();
    delete process.env.MODAL_START_RUN_ENDPOINT;
    delete process.env.MODAL_RESEARCH_TOKEN;
  });
});
