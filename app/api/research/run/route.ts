import { NextRequest, NextResponse } from "next/server";
import { toUiResearchRun, type PythonRunResult } from "@/lib/research/pythonRunAdapter";

// The research route is now a Python runtime proxy. Synchronous Modal calls may hold
// this function open briefly; long runs should use start_run + get_run polling.
export const maxDuration = 60;

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as {
      project_description?: string;
      demo_documents?: Array<{ name: string; type: string; text: string }>;
      provided_estimates?: Record<string, string | number>;
    };
    const input = {
      project_description: body.project_description ?? "",
      demo_documents: body.demo_documents ?? [],
      provided_estimates: body.provided_estimates ?? {},
    };

    const syncEndpoint = process.env.PYTHON_RESEARCH_RUN_SYNC_ENDPOINT;
    if (syncEndpoint) {
      const pythonRun = await postPythonRun(syncEndpoint, input);
      return NextResponse.json(toUiResearchRun(pythonRun));
    }

    const startEndpoint = process.env.PYTHON_RESEARCH_START_RUN_ENDPOINT;
    if (startEndpoint) {
      if (!process.env.PYTHON_RESEARCH_GET_RUN_ENDPOINT) {
        throw new Error("PYTHON_RESEARCH_GET_RUN_ENDPOINT must be configured when PYTHON_RESEARCH_START_RUN_ENDPOINT is set");
      }
      const pythonRun = await postPythonRun(startEndpoint, input);
      return NextResponse.json(shouldAdaptPythonRun(pythonRun) ? toUiResearchRun(pythonRun) : pythonRun);
    }

    throw new Error("Configure PYTHON_RESEARCH_RUN_SYNC_ENDPOINT or PYTHON_RESEARCH_START_RUN_ENDPOINT to run research");
  } catch (error) {
    return NextResponse.json(
      {
        run_id: "run_failed",
        status: "failed",
        error: error instanceof Error ? error.message : "Unknown research run failure"
      },
      { status: 500 }
    );
  }
}

async function postPythonRun(endpoint: string, input: { project_description: string; demo_documents: Array<{ name: string; type: string; text: string }>; provided_estimates: Record<string, string | number> }): Promise<PythonRunResult> {
  const resp = await fetch(endpoint, {
    method: "POST",
    headers: pythonHeaders(),
    body: JSON.stringify(input),
  });
  if (!resp.ok) throw new Error(`Python research endpoint HTTP ${resp.status}`);
  return await resp.json() as PythonRunResult;
}

function pythonHeaders(): HeadersInit {
  const headers: Record<string, string> = { "content-type": "application/json" };
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
