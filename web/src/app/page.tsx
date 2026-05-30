"use client";

import { useState } from "react";
import type { Determination, ResearchRun } from "@/lib/researchTypes";
import { runResearch } from "@/lib/runResearch";
import { ProjectInput } from "@/components/ProjectInput";
import { ResearchGraph } from "@/components/ResearchGraph";
import { TracePanel } from "@/components/TracePanel";
import { VerificationSummary } from "@/components/VerificationSummary";
import { ApplicabilityMatrix } from "@/components/ApplicabilityMatrix";
import { EvidenceDrawer } from "@/components/EvidenceDrawer";
import { ReportPanel } from "@/components/ReportPanel";

const SOCAL_DEMO_DESCRIPTION =
  "A Los Angeles County manufacturer is adding a coating booth and storing 60 gallons of a new flammable solvent. NAICS 332813, SIC 3471.";

export default function Home() {
  const [projectDescription, setProjectDescription] = useState("");
  const [run, setRun] = useState<ResearchRun | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [selected, setSelected] = useState<Determination | null>(null);
  const [usedFallback, setUsedFallback] = useState(false);

  async function handleRun() {
    setIsRunning(true);
    setSelected(null);
    const result = await runResearch(projectDescription);
    setRun(result.run);
    setUsedFallback(result.usedFallback);
    setIsRunning(false);
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <section className="mx-auto grid max-w-7xl gap-4 p-4 lg:grid-cols-[320px_minmax(0,1fr)_320px]">
        {usedFallback && (
          <p className="rounded bg-amber-900/50 px-3 py-2 text-xs text-amber-200 lg:col-span-3">
            Live API unavailable — showing cached demo run.
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
      <EvidenceDrawer run={run} determination={selected} onClose={() => setSelected(null)} />
    </main>
  );
}
