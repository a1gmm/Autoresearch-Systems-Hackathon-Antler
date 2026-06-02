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
    delete process.env.RESEARCH_RUNTIME;
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete process.env.PYTHON_RESEARCH_RUN_SYNC_ENDPOINT;
    delete process.env.PYTHON_RESEARCH_START_RUN_ENDPOINT;
    delete process.env.PYTHON_RESEARCH_GET_RUN_ENDPOINT;
    delete process.env.RESEARCH_RUNTIME;
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
});
