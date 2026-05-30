import type {
  CoverageFamily,
  CoverageFamilyStatus,
  Determination,
  EvidenceBundle,
  RegulatoryAngle,
  RepairTicket,
  ResearchHypothesis,
  ResearchRun,
  ResearchTask,
  VerificationVerdict,
} from "./researchTypes";

export type GraphHypothesisNode = ResearchHypothesis & { tasks: ResearchTask[] };
export type GraphAngleNode = RegulatoryAngle & { hypotheses: GraphHypothesisNode[] };
export type GraphFamilyNode = CoverageFamilyStatus & { angles: GraphAngleNode[] };

export function buildCoverageTree(run: ResearchRun): GraphFamilyNode[] {
  const tasksByHypothesis = new Map<string, ResearchTask[]>();
  for (const task of run.research_tasks) {
    const list = tasksByHypothesis.get(task.hypothesis_id) ?? [];
    list.push(task);
    tasksByHypothesis.set(task.hypothesis_id, list);
  }

  const hypothesesByAngle = new Map<string, GraphHypothesisNode[]>();
  for (const hypothesis of run.research_graph) {
    const node: GraphHypothesisNode = {
      ...hypothesis,
      tasks: tasksByHypothesis.get(hypothesis.id) ?? [],
    };
    const list = hypothesesByAngle.get(hypothesis.angle_id) ?? [];
    list.push(node);
    hypothesesByAngle.set(hypothesis.angle_id, list);
  }

  const anglesByFamily = new Map<CoverageFamily, GraphAngleNode[]>();
  for (const angle of run.regulatory_angles) {
    const node: GraphAngleNode = {
      ...angle,
      hypotheses: hypothesesByAngle.get(angle.id) ?? [],
    };
    const list = anglesByFamily.get(angle.family) ?? [];
    list.push(node);
    anglesByFamily.set(angle.family, list);
  }

  return run.coverage_family_statuses.map((family) => ({
    ...family,
    angles: anglesByFamily.get(family.family) ?? [],
  }));
}

export function getWorkerCount(run: ResearchRun): number {
  return run.research_tasks.length;
}

export function getEvidenceForHypothesis(
  run: ResearchRun,
  hypothesisId: string,
): EvidenceBundle | undefined {
  return run.evidence_bundles.find((bundle) => bundle.hypothesis_id === hypothesisId);
}

export function getVerdictForHypothesis(
  run: ResearchRun,
  hypothesisId: string,
): VerificationVerdict | undefined {
  return run.verification_verdicts.find((verdict) => verdict.hypothesis_id === hypothesisId);
}

export function getRepairsForHypothesis(run: ResearchRun, hypothesisId: string): RepairTicket[] {
  return run.repair_tickets.filter((ticket) => ticket.hypothesis_id === hypothesisId);
}

export type EvidenceView = {
  determination: Determination;
  evidence?: EvidenceBundle;
  verdict?: VerificationVerdict;
  repairs: RepairTicket[];
};

export function buildEvidenceView(run: ResearchRun, determination: Determination): EvidenceView {
  const id = determination.hypothesis_id;
  return {
    determination,
    evidence: id ? getEvidenceForHypothesis(run, id) : undefined,
    verdict: id ? getVerdictForHypothesis(run, id) : undefined,
    repairs: id ? getRepairsForHypothesis(run, id) : [],
  };
}
