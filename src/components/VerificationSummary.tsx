"use client";

import type { ResearchRun } from "@/lib/research/types";

export function VerificationSummary({ run }: { run: ResearchRun | null }) {
  if (!run) {
    return (
      <div className="rounded border border-slate-800 bg-slate-900 p-4 text-sm text-slate-500">
        Verification summary appears after a run.
      </div>
    );
  }

  const verdicts = run.verification_verdicts;
  const passed = verdicts.filter((verdict) => verdict.verdict === "pass").length;
  const needsReview = verdicts.filter((verdict) => verdict.verdict === "needs_review").length;
  const failed = verdicts.filter((verdict) => verdict.verdict === "fail").length;

  return (
    <div className="rounded border border-slate-800 bg-slate-900 p-4">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">Verification</h2>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-slate-400">Jurisdictions</dt>
        <dd>{run.jurisdiction_stack.join(", ")}</dd>
        <dt className="text-slate-400">Passed</dt>
        <dd className="text-emerald-300">{passed}</dd>
        <dt className="text-slate-400">Needs review</dt>
        <dd className="text-amber-300">{needsReview}</dd>
        <dt className="text-slate-400">Failed</dt>
        <dd className="text-red-400">{failed}</dd>
        <dt className="text-slate-400">Repair tickets</dt>
        <dd>{run.repair_tickets.length}</dd>
      </dl>
    </div>
  );
}
