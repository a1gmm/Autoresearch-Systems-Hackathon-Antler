import { NextRequest, NextResponse } from "next/server";
import { runResearch } from "@/lib/research/run";
import { isStoreConfigured } from "@/lib/research/store/supabaseStore";
import { enqueueRun } from "@/lib/research/durable/durableRun";
import { toUiResearchRun, type PythonRunResult } from "@/lib/research/pythonRunAdapter";

// Hold the serverless function open as long as the plan allows. Vercel REJECTS the
// deploy if this exceeds the plan's ceiling (800 failed → the plan caps lower), so we
// use 60s — the proven-good value the intake route already deploys with. The Modal
// worker itself runs up to 600s (not subject to Vercel limits); a live run that needs
// longer than the Vercel route allows is the durable Function.spawn+poll case (deferred).
export const maxDuration = 60;

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as {
      project_description?: string;
      demo_documents?: Array<{ name: string; type: string; text: string }>;
    };
    const input = {
      project_description: body.project_description ?? "",
      demo_documents: body.demo_documents ?? [],
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

    if (process.env.RESEARCH_RUNTIME === "durable" && isStoreConfigured()) {
      const { run_id, status } = await enqueueRun(input);
      return NextResponse.json({ run_id, status });
    }

    const run = await runResearch(input);

    return NextResponse.json(run);
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

async function postPythonRun(endpoint: string, input: { project_description: string; demo_documents: Array<{ name: string; type: string; text: string }> }): Promise<PythonRunResult> {
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
