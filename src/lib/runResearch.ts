import type { ResearchRun } from "@/lib/research/types";

// Calls Person A's in-app research engine. The endpoint runs on local fixtures,
// so no external network is required for the demo.
export async function runResearch(projectDescription: string): Promise<ResearchRun> {
  const response = await fetch("/api/research/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_description: projectDescription, demo_documents: [] }),
  });

  const payload = (await response.json()) as ResearchRun | { error?: string };

  if (!response.ok) {
    const message = "error" in payload && payload.error ? payload.error : "Research run failed";
    throw new Error(message);
  }

  return payload as ResearchRun;
}
