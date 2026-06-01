// Minimal propose_map_entry: stage a regime the orchestrator proposed but that is
// NOT in the program registry. NEVER asserted — always human_verified=false and
// needs_review, per design E3 (un-registried proposals hard-flag, never asserted).
export type StagedRegime = {
  id: string;
  family: string; // may be a CoverageFamily value or a free-form novel label
  rationale: string;
  human_verified: false;
  status: "needs_review";
};

let seq = 0;

export function stageNovelRegime(family: string, rationale: string): StagedRegime {
  seq += 1;
  return {
    id: `staged-${seq}`,
    family,
    rationale,
    human_verified: false,
    status: "needs_review",
  };
}
