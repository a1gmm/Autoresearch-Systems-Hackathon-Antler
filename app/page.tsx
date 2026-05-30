"use client";

import { useState } from "react";
import type { ResearchRun } from "@/lib/research/types";
import { runResearch } from "@/lib/runResearch";
import { ProjectInput } from "@/components/ProjectInput";
import { ResearchGraph } from "@/components/ResearchGraph";
import { TracePanel } from "@/components/TracePanel";
import { VerificationSummary } from "@/components/VerificationSummary";
import { ApplicabilityMatrix, type MatrixSelection } from "@/components/ApplicabilityMatrix";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { ReportPanel } from "@/components/ReportPanel";

const SOCAL_DEMO_DESCRIPTION =
  "A Los Angeles County manufacturer is adding a coating booth and storing 60 gallons of a new flammable solvent. NAICS 332813, SIC 3471.";

export default function Home() {
  const [projectDescription, setProjectDescription] = useState("");
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<MatrixSelection | null>(null);

  async function handleRun() {
    setIsRunning(true);
    setSelected(null);
    setError(null);
    try {
      const result = await runResearch(projectDescription);
      setRun(result);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Research run failed");
    } finally {
      setIsRunning(false);
    }
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <section className="mx-auto grid max-w-7xl gap-4 p-4 lg:grid-cols-[320px_minmax(0,1fr)_320px]">
        {error && (
          <p className="rounded bg-red-900/50 px-3 py-2 text-xs text-red-200 lg:col-span-3">
            Research run failed: {error}
          </p>
        )}
        <ProjectInput
          value={projectDescription}
          onChange={setProjectDescription}
          onLoadDemo={() => setProjectDescription(SOCAL_DEMO_DESCRIPTION)}
          onRun={handleRun}
          isRunning={isRunning}
          runStatus={run?.status ?? "idle"}
        />
        <div className="flex flex-col gap-4">
          <ResearchGraph run={run} />
          <TracePanel run={run} />
        </div>
        <VerificationSummary run={run} />
        <div className="lg:col-span-3">
          <ApplicabilityMatrix run={run} selected={selected} onSelect={setSelected} />
        </div>
        <div className="lg:col-span-3">
          <ReportPanel run={run} />
        </div>
      </section>
      <EvidenceDrawer run={run} selected={selected} onClose={() => setSelected(null)} />
    </main>
  );
}
