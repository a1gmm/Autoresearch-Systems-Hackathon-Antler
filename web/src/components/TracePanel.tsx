"use client";

import type { ResearchRun, TraceEvent } from "@/lib/researchTypes";
import { getWorkerCount } from "@/lib/researchSelectors";

const STATUS_STYLES: Record<TraceEvent["status"], string> = {
  queued: "text-slate-400",
  running: "text-sky-300",
  done: "text-emerald-300",
  failed: "text-red-400",
  needs_review: "text-amber-300",
};

export function TracePanel({ run }: { run: ResearchRun | null }) {
  if (!run) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">
        Trace will stream here after a run.
      </div>
    );
  }

  const events = [...run.trace_events].sort((a, b) => a.ts.localeCompare(b.ts));

  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Swarm trace</h2>
        <span className="rounded bg-slate-800 px-2 py-1 text-xs">
          {getWorkerCount(run)} workers from scoped graph
        </span>
      </div>
      <ol className="flex flex-col gap-2">
        {events.map((event) => {
          const highlight = event.status === "failed" || event.status === "needs_review";
          return (
            <li key={event.id} className={`rounded px-2 py-1 text-xs ${highlight ? "bg-slate-800" : ""}`}>
              <span className={`font-semibold ${STATUS_STYLES[event.status]}`}>
                {event.actor} · {event.phase}
              </span>
              <span className="ml-2 text-slate-300">{event.message}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
