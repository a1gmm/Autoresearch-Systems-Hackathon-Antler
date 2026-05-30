"use client";

import type { RunStatus } from "@/lib/research/types";

type Props = {
  value: string;
  onChange: (value: string) => void;
  onLoadDemo: () => void;
  onRun: () => void;
  isRunning: boolean;
  runStatus: RunStatus;
};

export function ProjectInput({ value, onChange, onLoadDemo, onRun, isRunning, runStatus }: Props) {
  return (
    <div className="flex flex-col gap-3 rounded border border-slate-800 bg-slate-900 p-4">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Project change</h2>
      <textarea
        className="min-h-32 resize-y rounded border border-slate-700 bg-slate-950 p-2 text-sm text-slate-100"
        placeholder="Describe the facility change..."
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
      <button
        type="button"
        onClick={onLoadDemo}
        className="rounded border border-slate-700 px-3 py-2 text-sm hover:bg-slate-800"
      >
        Load SoCal manufacturing demo
      </button>
      <button
        type="button"
        onClick={onRun}
        disabled={isRunning || value.trim().length === 0}
        className="rounded bg-emerald-600 px-3 py-2 text-sm font-semibold text-white disabled:opacity-40"
      >
        {isRunning ? "Running..." : "Run research swarm"}
      </button>
      <p className="text-xs text-slate-500">Run status: {runStatus}</p>
    </div>
  );
}
