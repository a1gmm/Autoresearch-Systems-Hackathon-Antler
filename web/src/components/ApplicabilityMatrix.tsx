"use client";

import type { Determination, ResearchRun } from "@/lib/researchTypes";

const APPLIES_STYLES: Record<Determination["applies"], string> = {
  yes: "text-emerald-300",
  no: "text-slate-400",
  needs_review: "text-amber-300",
};

type Props = {
  run: ResearchRun | null;
  selected: Determination | null;
  onSelect: (determination: Determination) => void;
};

export function ApplicabilityMatrix({ run, selected, onSelect }: Props) {
  if (!run) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">
        Applicability matrix appears after a run.
      </div>
    );
  }

  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Applicability matrix</h2>
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="text-xs uppercase text-slate-500">
            <th className="py-2 pr-2">Requirement</th>
            <th className="py-2 pr-2">Applies</th>
            <th className="py-2 pr-2">Trigger</th>
            <th className="py-2 pr-2">Project fact</th>
            <th className="py-2 pr-2">Confidence</th>
            <th className="py-2 pr-2">Status</th>
          </tr>
        </thead>
        <tbody>
          {run.determinations.map((determination) => {
            const rowKey = determination.hypothesis_id ?? determination.requirement;
            const isSelected = selected
              ? (selected.hypothesis_id ?? selected.requirement) === rowKey
              : false;
            return (
              <tr
                key={rowKey}
                onClick={() => onSelect(determination)}
                className={`cursor-pointer border-t border-slate-800 ${
                  isSelected ? "bg-slate-800" : "hover:bg-slate-800/40"
                } ${determination.review_flag ? "border-l-2 border-l-amber-600" : ""}`}
              >
                <td className="py-2 pr-2">{determination.requirement}</td>
                <td className={`py-2 pr-2 font-semibold ${APPLIES_STYLES[determination.applies]}`}>
                  {determination.applies}
                </td>
                <td className="py-2 pr-2 text-slate-300">{determination.trigger}</td>
                <td className="py-2 pr-2 text-slate-300">{determination.project_fact}</td>
                <td className="py-2 pr-2">{Math.round(determination.confidence * 100)}%</td>
                <td className="py-2 pr-2">
                  {determination.verified ? (
                    <span className="text-emerald-300">verified</span>
                  ) : (
                    <span className="text-amber-300">needs review</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">Select a row to open the evidence drawer.</p>
    </div>
  );
}
