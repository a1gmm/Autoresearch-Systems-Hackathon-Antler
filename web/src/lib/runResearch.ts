import type { ResearchRun } from "./researchTypes";
import { demoResearchRun } from "./demoResearchRun";

export type RunResult = { run: ResearchRun; usedFallback: boolean };

export async function runResearch(projectDescription: string): Promise<RunResult> {
  try {
    const response = await fetch("/api/research/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_description: projectDescription, demo_documents: [] }),
    });

    const payload = (await response.json()) as ResearchRun | { error: string; run?: ResearchRun };

    if (!response.ok) {
      if ("run" in payload && payload.run) return { run: payload.run, usedFallback: false };
      throw new Error("error" in payload ? payload.error : "Research run failed");
    }

    return { run: payload as ResearchRun, usedFallback: false };
  } catch {
    return { run: demoResearchRun, usedFallback: true };
  }
}
