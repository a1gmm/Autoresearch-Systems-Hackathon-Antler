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
});
