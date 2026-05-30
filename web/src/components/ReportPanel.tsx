"use client";

import type { ResearchRun } from "@/lib/researchTypes";

export function ReportPanel({ run }: { run: ResearchRun | null }) {
  if (!run) return null;
  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">Report</h2>
      <p className="whitespace-pre-wrap text-sm text-slate-300">{run.report_markdown}</p>
    </div>
  );
}
