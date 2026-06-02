import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

function req(body: unknown): NextRequest {
  return new NextRequest("http://test.local/api/research/run", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function loadPOST() {
  vi.resetModules();
  const mod = await import("../route");
  return mod.POST;
}

describe("POST /api/research/run Python runtime config", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    delete process.env.PYTHON_RESEARCH_RUN_SYNC_ENDPOINT;
    delete process.env.PYTHON_RESEARCH_START_RUN_ENDPOINT;
    delete process.env.PYTHON_RESEARCH_GET_RUN_ENDPOINT;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete process.env.PYTHON_RESEARCH_RUN_SYNC_ENDPOINT;
    delete process.env.PYTHON_RESEARCH_START_RUN_ENDPOINT;
    delete process.env.PYTHON_RESEARCH_GET_RUN_ENDPOINT;
  });

  it("rejects async Python start configuration without the matching get_run endpoint", async () => {
    process.env.PYTHON_RESEARCH_START_RUN_ENDPOINT = "https://python.example/start";
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const POST = await loadPOST();
    const res = await POST(req({ project_description: "queued run" }));
    const data = await res.json();

    expect(res.status).toBe(500);
    expect(data.status).toBe("failed");
    expect(data.error).toContain("PYTHON_RESEARCH_GET_RUN_ENDPOINT");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("fails fast instead of falling back to the retired TypeScript runtime", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const POST = await loadPOST();
    const res = await POST(req({ project_description: "no endpoints configured" }));
    const data = await res.json();

    expect(res.status).toBe(500);
    expect(data.status).toBe("failed");
    expect(data.error).toContain("PYTHON_RESEARCH_RUN_SYNC_ENDPOINT");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("proxies sync Python runs and adapts the payload", async () => {
    process.env.PYTHON_RESEARCH_RUN_SYNC_ENDPOINT = "https://python.example/run_sync";
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        run_id: "run_sync",
        status: "done",
        result: {
          determination: {
            status: "verified",
            trusted_hypotheses: ["H-AIR-201"],
            needs_review_hypotheses: [],
            reasons: ["All researched hypotheses passed verification."],
          },
          evidence: [],
          verdicts: [
            {
              hypothesis_id: "H-AIR-201",
              verdict: "pass",
              checks: {},
              confidence: 0.91,
              repair_tickets: [],
            },
          ],
        },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const POST = await loadPOST();
    const res = await POST(req({ project_description: "sync run" }));
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.run_id).toBe("run_sync");
    expect(data.status).toBe("done");
    expect(data.determinations).toEqual([
      expect.objectContaining({ requirement: "H-AIR-201", verified: true }),
    ]);
    expect(fetchMock).toHaveBeenCalledWith(
      "https://python.example/run_sync",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("proxies async Python starts when get_run is configured", async () => {
    process.env.PYTHON_RESEARCH_START_RUN_ENDPOINT = "https://python.example/start";
    process.env.PYTHON_RESEARCH_GET_RUN_ENDPOINT = "https://python.example/get";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ run_id: "run_async", status: "queued" }));
    vi.stubGlobal("fetch", fetchMock);

    const POST = await loadPOST();
    const res = await POST(req({ project_description: "async run" }));
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data).toEqual({ run_id: "run_async", status: "queued" });
    expect(fetchMock).toHaveBeenCalledWith(
      "https://python.example/start",
      expect.objectContaining({ method: "POST" }),
    );
  });
});

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}
