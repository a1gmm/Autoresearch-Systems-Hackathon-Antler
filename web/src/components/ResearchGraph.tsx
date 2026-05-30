"use client";

import type { ResearchRun } from "@/lib/researchTypes";
import { buildCoverageTree } from "@/lib/researchSelectors";

const STATUS_STYLES: Record<string, string> = {
  active: "border-emerald-700 text-emerald-300",
  blocked_missing_fact: "border-amber-700 text-amber-300",
  out_of_scope: "border-slate-700 text-slate-500",
  discovery_candidate: "border-purple-700 text-purple-300",
};

function statusClass(status: string): string {
  return STATUS_STYLES[status] ?? "border-slate-700 text-slate-300";
}

export function ResearchGraph({ run }: { run: ResearchRun | null }) {
  if (!run) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">
        Research graph will appear after a run.
      </div>
    );
  }

  const tree = buildCoverageTree(run);

  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Coverage graph</h2>
      <ul className="flex flex-col gap-3">
        {tree.map((family) => (
          <li key={family.id} className={`rounded border-l-2 pl-3 ${statusClass(family.status)}`}>
            <div className="text-sm font-semibold">
              {family.family} <span className="text-xs font-normal">({family.status})</span>
            </div>
            <p className="text-xs text-slate-400">{family.reason}</p>
            <ul className="mt-2 flex flex-col gap-2">
              {family.angles.map((angle) => (
                <li key={angle.id} className={`rounded border-l-2 pl-3 ${statusClass(angle.status)}`}>
                  <div className="text-xs font-semibold">{angle.label}</div>
                  <ul className="mt-1 flex flex-col gap-1">
                    {angle.hypotheses.map((hypothesis) => (
                      <li key={hypothesis.id} className="rounded border-l-2 border-slate-700 pl-3">
                        <div className="text-xs text-slate-200">{hypothesis.question}</div>
                        <div className="text-[11px] text-slate-500">
                          {hypothesis.tasks.length} task{hypothesis.tasks.length === 1 ? "" : "s"}:{" "}
                          {hypothesis.tasks.map((task) => task.assigned_agent).join(", ") || "none"}
                        </div>
                      </li>
                    ))}
                  </ul>
                </li>
              ))}
              {family.angles.length === 0 && (
                <li className="text-[11px] text-slate-500">No angle pursued for this family.</li>
              )}
            </ul>
          </li>
        ))}
      </ul>
    </div>
  );
}
