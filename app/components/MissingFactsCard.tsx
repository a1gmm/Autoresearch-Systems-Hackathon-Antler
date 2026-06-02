"use client";
import { useStore } from "@/lib/ui/store";
import { getInformationRequests, getScenarios } from "@/lib/ui/selectors";
import { AlertTriangle, GitCompare } from "lucide-react";
import { motion } from "framer-motion";

export function MissingFactsCard() {
  const run = useStore((s) => s.run);
  const requests = run ? getInformationRequests(run) : [];
  const scenarios = run ? getScenarios(run) : [];
  if (requests.length === 0 && scenarios.length === 0) return null;
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
            disabled
            placeholder={request.field}
            title={request.field}
            className="mt-1.5 w-full px-2 py-1.5 bg-slate-950/60 text-slate-400 border border-slate-700/40 rounded-lg text-xs cursor-not-allowed"
          />
        </div>
      ))}
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
