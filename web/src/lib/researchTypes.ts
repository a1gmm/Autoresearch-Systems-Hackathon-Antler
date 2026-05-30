export type RunStatus = "idle" | "queued" | "running" | "partial" | "needs_review" | "done" | "failed";

export type CoverageFamily =
  | "air"
  | "stormwater"
  | "hazmat"
  | "waste"
  | "wastewater"
  | "land_use"
  | "fire_code"
  | "ceqa"
  | "osha";

export type CoverageFamilyStatus = {
  id: string;
  family: CoverageFamily;
  status: "active" | "blocked_missing_fact" | "out_of_scope" | "discovery_candidate";
  reason: string;
  project_facts_considered: string[];
  missing_facts: string[];
};

export type RegulatoryAngle = {
  id: string;
  family: CoverageFamily;
  label: string;
  reason: string;
  triggering_facts: string[];
  status: "active" | "blocked_missing_fact" | "out_of_scope" | "discovery_candidate";
};

export type ResearchHypothesis = {
  id: string;
  angle_id: string;
  question: string;
  claim_to_test?: string;
  required_facts: string[];
  expected_source_type: "statute" | "regulation" | "agency_guidance" | "permit_portal" | "technical_doc";
  success_criteria: string[];
  dependencies: string[];
};

export type ResearchTask = {
  task_id: string;
  hypothesis_id: string;
  assigned_agent: string;
  allowed_tools: string[];
  blocked_tools: string[];
  budget: {
    max_sources: number;
    max_runtime_seconds: number;
    max_model_calls: number;
  };
};

export type EvidenceBundle = {
  hypothesis_id: string;
  sources: Array<{
    url: string;
    source_name: string;
    authority_rank: number;
    fetched_at: string;
    content_hash: string;
    effective_date: string | null;
    quote: string;
  }>;
  extracted_claims: Array<{
    field: string;
    value: string;
    source_url: string;
    quote: string;
    confidence: number;
  }>;
  researcher_conclusion: "applies" | "does_not_apply" | "needs_review";
  uncertainties: string[];
};

export type RepairTicket = {
  ticket_id: string;
  hypothesis_id: string;
  failure_type: "grounding_failed" | "source_failed" | "missing_fact" | "invalid_json" | "conflict";
  failed_check: string;
  observed_problem: string;
  repair_action: string;
  max_attempts_remaining: number;
};

export type VerificationVerdict = {
  hypothesis_id: string;
  verdict: "pass" | "fail" | "needs_review";
  checks: Record<string, { pass: boolean; reason: string }>;
  confidence: number;
  repair_tickets: RepairTicket[];
};

export type Determination = {
  requirement: string;
  applies: "yes" | "no" | "needs_review";
  trigger: string;
  project_fact: string;
  citation: string;
  quote: string;
  source_url: string;
  confidence: number;
  verified: boolean;
  review_flag: boolean;
  hypothesis_id?: string;
};

export type TraceEvent = {
  id: string;
  run_id: string;
  ts: string;
  actor: string;
  phase: string;
  status: "queued" | "running" | "done" | "failed" | "needs_review";
  message: string;
  artifact_id?: string;
};

export type ResearchRun = {
  run_id: string;
  status: RunStatus;
  project_facts: Record<string, unknown>;
  jurisdiction_stack: string[];
  coverage_family_statuses: CoverageFamilyStatus[];
  regulatory_angles: RegulatoryAngle[];
  research_graph: ResearchHypothesis[];
  research_tasks: ResearchTask[];
  evidence_bundles: EvidenceBundle[];
  verification_verdicts: VerificationVerdict[];
  repair_tickets: RepairTicket[];
  determinations: Determination[];
  trace_events: TraceEvent[];
  report_markdown: string;
};
