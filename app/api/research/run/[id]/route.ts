import { NextRequest, NextResponse } from "next/server";
import { toUiResearchRun, type PythonRunResult } from "@/lib/research/pythonRunAdapter";

export const maxDuration = 60;

export async function GET(_request: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const endpoint = process.env.PYTHON_RESEARCH_GET_RUN_ENDPOINT;
    if (endpoint) {
      const pythonRun = await getPythonRun(endpoint, id);
      if (pythonRun === null) {
        return NextResponse.json({ run_id: id, status: "failed", error: `run ${id} was not found` }, { status: 404 });
      }
      return NextResponse.json(shouldAdaptPythonRun(pythonRun) ? toUiResearchRun(pythonRun) : pythonRun);
    }

    throw new Error("PYTHON_RESEARCH_GET_RUN_ENDPOINT must be configured to read research runs");
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error";
    const status = /not found/i.test(message) ? 404 : 500;
    return NextResponse.json({ run_id: id, status: "failed", error: message }, { status });
  }
}

async function getPythonRun(endpoint: string, runId: string): Promise<PythonRunResult | null> {
  const resp = await fetch(pythonRunUrl(endpoint, runId), {
    method: "GET",
    headers: pythonHeaders(),
  });
  if (!resp.ok) throw new Error(`Python research get_run HTTP ${resp.status}`);
  return await resp.json() as PythonRunResult | null;
}

function pythonRunUrl(endpoint: string, runId: string): string {
  if (endpoint.includes("{id}")) return endpoint.replaceAll("{id}", encodeURIComponent(runId));
  const separator = endpoint.includes("?") ? "&" : "?";
  return `${endpoint}${separator}run_id=${encodeURIComponent(runId)}`;
}

function pythonHeaders(): HeadersInit {
  const headers: Record<string, string> = {};
  const token = process.env.MODAL_RESEARCH_TOKEN;
  if (token) {
    headers.authorization = `Bearer ${token}`;
    headers["x-research-token"] = token;
  }
  return headers;
}

function shouldAdaptPythonRun(payload: PythonRunResult): boolean {
  return Boolean(
    payload.result ||
      payload.determinations ||
      payload.information_requests ||
      payload.scenarios ||
      payload.report_markdown ||
      payload.verdicts ||
      payload.evidence,
  );
}
