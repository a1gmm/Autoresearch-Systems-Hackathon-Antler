import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

async function loadGET() {
  vi.resetModules();
  const mod = await import("../route");
  return mod.GET;
}

describe("GET /api/research/run/:id Python runtime proxy", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    process.env.PYTHON_RESEARCH_GET_RUN_ENDPOINT = "https://python.example/get";
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete process.env.PYTHON_RESEARCH_GET_RUN_ENDPOINT;
  });

  it("returns 404 when Python get_run returns null", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response("null", {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const GET = await loadGET();
    const res = await GET(
      new NextRequest("http://test.local/api/research/run/run_missing"),
      { params: Promise.resolve({ id: "run_missing" }) },
    );
    const data = await res.json();

    expect(res.status).toBe(404);
    expect(data).toEqual({
      run_id: "run_missing",
      status: "failed",
      error: "run run_missing was not found",
    });
    expect(fetchMock).toHaveBeenCalledWith(
      "https://python.example/get?run_id=run_missing",
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("fails fast instead of falling back to the retired TypeScript durable runtime", async () => {
    delete process.env.PYTHON_RESEARCH_GET_RUN_ENDPOINT;
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);

    const GET = await loadGET();
    const res = await GET(
      new NextRequest("http://test.local/api/research/run/run_no_endpoint"),
      { params: Promise.resolve({ id: "run_no_endpoint" }) },
    );
    const data = await res.json();

    expect(res.status).toBe(500);
    expect(data).toEqual({
      run_id: "run_no_endpoint",
      status: "failed",
      error: "PYTHON_RESEARCH_GET_RUN_ENDPOINT must be configured to read research runs",
    });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("proxies and adapts Python get_run payloads", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({
        run_id: "run_get",
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
      }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const GET = await loadGET();
    const res = await GET(
      new NextRequest("http://test.local/api/research/run/run_get"),
      { params: Promise.resolve({ id: "run_get" }) },
    );
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.run_id).toBe("run_get");
    expect(data.determinations).toEqual([
      expect.objectContaining({ requirement: "H-AIR-201", verified: true }),
    ]);
  });
});
