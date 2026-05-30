"use client";

import type { ResearchRun } from "@/lib/research/types";
import { buildEvidenceView } from "@/lib/researchSelectors";
import type { MatrixSelection } from "@/components/ApplicabilityMatrix";

type Props = {
  run: ResearchRun | null;
  selected: MatrixSelection | null;
  onClose: () => void;
};

export function EvidenceDrawer({ run, selected, onClose }: Props) {
  if (!run || !selected) return null;

  const { determination, hypothesisId } = selected;
  const view = buildEvidenceView(run, hypothesisId);

  return (
    <aside className="fixed inset-y-0 right-0 z-10 w-full max-w-md overflow-y-auto border-l border-slate-800 bg-slate-900 p-4 shadow-xl">
      <div className="mb-3 flex items-start justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Evidence</h2>
        <button type="button" onClick={onClose} className="text-slate-400 hover:text-slate-100">
          Close
        </button>
      </div>

      <h3 className="text-base font-semibold">{determination.requirement}</h3>
      <p className="text-sm text-slate-300">
        Applies: {determination.applies} · confidence {Math.round(determination.confidence * 100)}%
      </p>

      <section className="mt-4">
        <h4 className="text-xs font-semibold uppercase text-slate-500">Sources</h4>
        {view.evidence && view.evidence.sources.length > 0 ? (
          view.evidence.sources.map((source) => (
            <div key={source.url} className="mt-2 rounded border border-slate-800 p-2 text-xs">
              <a href={source.url} className="text-sky-300 underline" target="_blank" rel="noreferrer">
                {source.source_name || source.url}
              </a>
              <p className="mt-1 italic text-slate-300">&ldquo;{source.quote}&rdquo;</p>
              <p className="mt-1 text-slate-500">hash: {source.content_hash}</p>
              <p className="text-slate-500">fetched: {source.fetched_at}</p>
              <p className="text-slate-500">effective: {source.effective_date ?? "unknown"}</p>
            </div>
          ))
        ) : (
          <p className="mt-1 text-xs text-slate-500">No source evidence (missing fact or blocked).</p>
        )}
      </section>

      <section className="mt-4">
        <h4 className="text-xs font-semibold uppercase text-slate-500">Verifier checks</h4>
        {view.verdict ? (
          <ul className="mt-2 flex flex-col gap-1 text-xs">
            {Object.entries(view.verdict.checks).map(([name, check]) => (
              <li key={name}>
                <span className={check.pass ? "text-emerald-300" : "text-red-400"}>
                  {check.pass ? "PASS" : "FAIL"}
                </span>{" "}
                <span className="text-slate-300">{name}</span>: {check.reason}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-xs text-slate-500">No verdict recorded.</p>
        )}
      </section>

      <section className="mt-4">
        <h4 className="text-xs font-semibold uppercase text-slate-500">Repair history</h4>
        {view.repairs.length > 0 ? (
          view.repairs.map((repair) => (
            <div key={repair.ticket_id} className="mt-2 rounded border border-amber-800 p-2 text-xs">
              <p className="font-semibold text-amber-300">{repair.failure_type}</p>
              <p className="text-slate-300">{repair.observed_problem}</p>
              <p className="text-slate-400">Action: {repair.repair_action}</p>
            </div>
          ))
        ) : (
          <p className="mt-1 text-xs text-slate-500">No repairs needed.</p>
        )}
      </section>
    </aside>
  );
}
