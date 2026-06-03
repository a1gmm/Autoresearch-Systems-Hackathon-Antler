"use client";
import { useState } from "react";
import { useStore } from "@/lib/ui/store";
import { getInformationRequests, getScenarios } from "@/lib/ui/selectors";
import { AlertTriangle, GitCompare, Play, Loader2 } from "lucide-react";
import { motion } from "framer-motion";

export function MissingFactsCard() {
  const run = useStore((s) => s.run);
  const startRun = useStore((s) => s.startRun);
  const isRunning = useStore((s) => s.isRunning);
  const lastInput = useStore((s) => s.lastInput);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const requests = run ? getInformationRequests(run) : [];
  const scenarios = run ? getScenarios(run) : [];
  if (requests.length === 0 && scenarios.length === 0) return null;

  const filled = Object.entries(answers).filter(([, v]) => v.trim().length > 0);
  function rerunWithFacts() {
    if (isRunning || filled.length === 0) return;
    const provided_estimates: Record<string, string> = {};
    for (const [field, value] of filled) provided_estimates[field] = value.trim();
    void startRun({
      project_description: lastInput?.project_description ?? "",
      demo_documents: lastInput?.demo_documents ?? [],
      provided_estimates: { ...(lastInput?.provided_estimates ?? {}), ...provided_estimates },
    });
  }
  return (
    <motion.div
      className="glass rounded-xl p-3"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      <div className="flex items-center gap-1.5 mb-2" style={{ fontSize: 11, letterSpacing: "0.22em", textTransform: "uppercase" as const, color: "#f59e0b", fontWeight: 600 }}>
        <AlertTriangle size={11} />
        Missing facts ({requests.length})
      </div>
      {requests.map((request) => (
        <div key={request.field} className="mb-2.5 last:mb-0">
          <div className="text-xs text-amber-400 font-medium">{request.question || request.field}</div>
          <div className="text-[11px] text-slate-400 mt-0.5">{request.why_needed}</div>
          <div className="text-[11px] text-slate-500">Blocks: {request.blocks.join(", ")}</div>
          <input
            value={answers[request.field] ?? ""}
            onChange={(e) => setAnswers((prev) => ({ ...prev, [request.field]: e.target.value }))}
            onKeyDown={(e) => {
              if (e.key === "Enter") rerunWithFacts();
            }}
            placeholder={request.field}
            title={request.field}
            disabled={isRunning}
            className="mt-1.5 w-full px-2 py-1.5 bg-slate-950/60 text-slate-100 border border-slate-700/40 rounded-lg text-xs placeholder:text-slate-500 focus:outline-none focus:border-cyan-600/50 transition-colors disabled:opacity-50"
          />
        </div>
      ))}
      <button
        type="button"
        onClick={rerunWithFacts}
        disabled={isRunning || filled.length === 0}
        className="mt-1 flex w-full items-center justify-center gap-1.5 rounded-lg bg-amber-600/90 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-amber-500 disabled:cursor-default disabled:opacity-40"
      >
        {isRunning ? <Loader2 size={12} className="animate-spin" /> : <Play size={12} />}
        Re-run with {filled.length || ""} fact{filled.length === 1 ? "" : "s"}
      </button>
      {scenarios.length > 0 && (
        <div className="mt-3 pt-3 border-t border-slate-800/60">
          <div className="flex items-center gap-1.5 mb-2 text-[11px] uppercase font-semibold text-cyan-300/80" style={{ letterSpacing: "0.16em" }}>
            <GitCompare size={11} />
            Scenario comparison
          </div>
          <div className="grid gap-2">
            {scenarios.map((scenario) => (
              <div key={scenario.id} className="rounded-lg border border-slate-800/70 bg-slate-950/35 p-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs font-semibold text-slate-100">{scenario.label}</div>
                  <div className="text-[10px] text-slate-500">{scenario.affects.join(", ")}</div>
                </div>
                {scenario.assumptions.map((assumption) => (
                  <div key={`${scenario.id}-${assumption.field}`} className="mt-1 text-[11px] text-slate-400">
                    <span className="text-slate-300">{assumption.field}</span>: {String(assumption.value)}
                    {assumption.unit ? ` ${assumption.unit}` : ""}
                    {assumption.provenance ? (
                      <span className="ml-1 text-slate-500">({assumption.provenance.replaceAll("_", " ")})</span>
                    ) : null}
                  </div>
                ))}
                {scenario.rationale && (
                  <div className="mt-1 text-[11px] text-slate-500">{scenario.rationale}</div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </motion.div>
  );
}
