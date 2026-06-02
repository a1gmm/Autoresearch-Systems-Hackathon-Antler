import type {
  CoverageFamily,
  CoverageFamilyStatus,
  Determination,
  EvidenceBundle,
  InformationRequest,
  MemoryUpdate,
  RegulatoryAngle,
  RepairTicket,
  ResearchHypothesis,
  ResearchRun,
  ResearchTask,
  RunStatus,
  Scenario,
  ScopePack,
  TraceEvent,
  VerificationVerdict,
} from "./types";

export type PythonRunResult = Record<string, unknown>;

type JsonObject = Record<string, unknown>;

const COVERAGE_FAMILIES: CoverageFamily[] = [
  "air",
  "stormwater",
  "hazmat",
  "waste",
  "wastewater",
  "land_use",
  "fire_code",
  "ceqa",
  "osha",
];

const COVERAGE_FAMILY_ALIASES: Array<[CoverageFamily, string[]]> = [
  ["air", ["air", "scaqmd", "aqmd", "rule-201", "rule-219", "rule-222", "title-v", "emissions", "permit-to-construct"]],
  ["stormwater", ["stormwater", "industrial-general-permit", "construction-general-permit", "stormwater-construction", "igp", "cgp"]],
  ["hazmat", ["hazmat", "hmbp", "ca-hmbp", "cupa", "hazardous-material", "hazardous-materials", "apsa", "spcc", "ca-apsa-spcc", "calarp", "ca-calarp-program", "ust", "ca-ust-program"]],
  ["waste", ["waste", "hazwaste", "hazardous-waste", "title22", "title-22", "epa-hazwaste-generator", "ca-title22-hazwaste", "universal-waste", "ca-universal-waste", "medical-waste", "ca-medical-waste"]],
  ["wastewater", ["wastewater", "pretreatment", "epa-pretreatment", "wdr", "npdes", "ca-wdr-npdes", "process-discharge"]],
  ["land_use", ["land-use", "land_use", "zoning", "planning"]],
  ["fire_code", ["fire-code", "fire_code", "fire", "cal-fire-code"]],
  ["ceqa", ["ceqa"]],
  ["osha", ["osha", "worker-safety", "workplace-safety"]],
];

const DEFAULT_SCOPE_PACK: ScopePack = {
  run_id: "",
  facility: {
    address: "",
    jurisdiction_stack: [],
    county: null,
    city: null,
    naics: null,
    sic: null,
  },
  project_change: {
    description: "",
    equipment: [],
    chemicals: [],
    waste_streams: [],
    disturbance_acres: null,
    process_discharge: null,
  },
  missing_facts: [],
  assumptions: [],
};

export function toUiResearchRun(pythonRun: PythonRunResult): ResearchRun {
  const result = objectValue(pythonRun.result);
  const scope = objectValue(pythonRun.scope_pack) ?? objectValue(result?.scope);
  const runId = stringValue(pythonRun.run_id) ?? stringValue(result?.run_id) ?? "run_unknown";
  const verdicts = coerceVerdicts(
    arrayValue(pythonRun.verification_verdicts) ??
      arrayValue(pythonRun.verdicts) ??
      arrayValue(result?.verdicts),
  );
  const repairTickets = coerceRepairTickets([
    ...(arrayValue(pythonRun.repair_tickets) ?? []),
    ...(arrayValue(result?.repair_tickets) ?? []),
    ...verdicts.flatMap((verdict) => verdict.repair_tickets),
  ]);
  const explicitDeterminations = coerceDeterminations(
    arrayValue(pythonRun.determinations) ??
      arrayValue(result?.determinations) ??
      arrayValue(objectValue(result?.report)?.determinations),
  );
  const informationRequests = coerceInformationRequests(
    arrayValue(pythonRun.information_requests) ??
      arrayValue(result?.information_requests),
  );
  const scenarios = coerceScenarios(
    arrayValue(pythonRun.scenarios) ??
      arrayValue(result?.scenarios),
  );
  const evidence = coerceEvidenceBundles(
    arrayValue(pythonRun.evidence_bundles) ??
      arrayValue(pythonRun.evidence) ??
      arrayValue(result?.evidence),
  );
  const determinations = explicitDeterminations.length > 0
    ? explicitDeterminations
    : coerceDeterminationsFromSingularResult(objectValue(result?.determination), verdicts, evidence);
  const coverageStatuses = coerceCoverageStatuses(
    arrayValue(pythonRun.coverage_family_statuses) ??
      arrayValue(objectValue(result?.report)?.coverage),
    informationRequests,
  );
  const researchGraph = coerceResearchGraph(
    arrayValue(pythonRun.research_graph) ?? arrayValue(result?.research_graph),
    determinations,
    evidence,
    coverageStatuses,
  );

  return {
    run_id: runId,
    status: coerceRunStatus(stringValue(pythonRun.status) ?? stringValue(objectValue(result?.determination)?.status)),
    project_facts: objectValue(pythonRun.project_facts) ?? {},
    jurisdiction_stack: stringArray(pythonRun.jurisdiction_stack) ?? stringArray(objectValue(scope)?.facility && objectValue(objectValue(scope)?.facility)?.jurisdiction_stack) ?? [],
    scope_pack: coerceScopePack(scope, runId),
    coverage_family_statuses: coverageStatuses,
    regulatory_angles: coerceArray<RegulatoryAngle>(arrayValue(pythonRun.regulatory_angles) ?? arrayValue(result?.regulatory_angles)),
    research_graph: researchGraph,
    research_tasks: coerceArray<ResearchTask>(arrayValue(pythonRun.research_tasks) ?? arrayValue(result?.research_tasks)),
    evidence_bundles: evidence,
    verification_verdicts: verdicts,
    repair_tickets: repairTickets,
    memory_updates: coerceArray<MemoryUpdate>(arrayValue(pythonRun.memory_updates) ?? arrayValue(result?.memory_updates)),
    determinations,
    trace_events: coerceTraceEvents(
      arrayValue(pythonRun.trace_events) ??
        arrayValue(result?.trace_events) ??
        arrayValue(pythonRun.raindrop_events),
      runId,
    ),
    report_markdown: coerceReportMarkdown(pythonRun, result),
    information_requests: informationRequests,
    scenarios,
    distrust_reasons: collectDistrustReasons(result, verdicts),
    sds_reviews: coerceArray(arrayValue(pythonRun.sds_reviews) ?? arrayValue(result?.sds_reviews)),
  };
}

function coerceRunStatus(status: string | undefined): RunStatus {
  if (!status) return "failed";
  if (status === "verified") return "done";
  if (status === "researching" || status === "verifying" || status === "repairing") return status;
  if (
    status === "idle" ||
    status === "queued" ||
    status === "scoping" ||
    status === "running" ||
    status === "planning" ||
    status === "synthesizing" ||
    status === "partial" ||
    status === "needs_information" ||
    status === "needs_review" ||
    status === "done" ||
    status === "failed"
  ) {
    return status;
  }
  return "running";
}

function coerceScopePack(value: unknown, runId: string): ScopePack {
  const obj = objectValue(value);
  if (!obj) return { ...DEFAULT_SCOPE_PACK, run_id: runId };
  const facility = objectValue(obj.facility);
  const projectChange = objectValue(obj.project_change);
  return {
    run_id: stringValue(obj.run_id) ?? runId,
    facility: {
      address: stringValue(facility?.address) ?? "",
      jurisdiction_stack: stringArray(facility?.jurisdiction_stack) ?? [],
      county: stringValue(facility?.county) ?? null,
      city: stringValue(facility?.city) ?? null,
      naics: stringValue(facility?.naics) ?? null,
      sic: stringValue(facility?.sic) ?? null,
    },
    project_change: {
      description: stringValue(projectChange?.description) ?? "",
      equipment: coerceArray(projectChange?.equipment),
      chemicals: coerceArray(projectChange?.chemicals),
      waste_streams: coerceArray(projectChange?.waste_streams),
      disturbance_acres: numberOrNull(projectChange?.disturbance_acres),
      process_discharge: booleanOrNull(projectChange?.process_discharge),
    },
    missing_facts: coerceArray(obj.missing_facts),
    assumptions: coerceArray(obj.assumptions),
  };
}

function coerceInformationRequests(values: unknown[] | undefined): InformationRequest[] {
  return (values ?? []).map((value) => {
    const obj = objectValue(value) ?? {};
    return {
      field: stringValue(obj.field) ?? "",
      question: stringValue(obj.question) ?? "",
      why_needed: stringValue(obj.why_needed) ?? "",
      blocks: stringArray(obj.blocks) ?? [],
    };
  });
}

function coerceScenarios(values: unknown[] | undefined): Scenario[] {
  return (values ?? []).map((value, index) => {
    const obj = objectValue(value) ?? {};
    return {
      id: stringValue(obj.id) ?? `scenario_${index + 1}`,
      label: stringValue(obj.label) ?? "expected",
      assumptions: (arrayValue(obj.assumptions) ?? []).map((assumption) => {
        const assumptionObj = objectValue(assumption) ?? {};
        return {
          field: stringValue(assumptionObj.field) ?? "",
          value: assumptionObj.value,
          unit: stringValue(assumptionObj.unit) ?? null,
          provenance: stringValue(assumptionObj.provenance) ?? "missing",
        };
      }),
      rationale: stringValue(obj.rationale) ?? "",
      affects: stringArray(obj.affects) ?? [],
    };
  });
}

function coerceVerdicts(values: unknown[] | undefined): VerificationVerdict[] {
  return (values ?? []).map((value) => {
    const obj = objectValue(value) ?? {};
    const checks = objectValue(obj.checks) ?? {};
    return {
      hypothesis_id: stringValue(obj.hypothesis_id) ?? "",
      verdict: coerceVerdictStatus(stringValue(obj.verdict)),
      checks: Object.fromEntries(
        Object.entries(checks).map(([name, check]) => {
          const checkObj = objectValue(check) ?? {};
          return [
            name,
            {
              pass: Boolean(checkObj.pass),
              reason: stringValue(checkObj.reason) ?? "",
            },
          ];
        }),
      ),
      confidence: numberOrDefault(obj.confidence, 0),
      repair_tickets: coerceRepairTickets(arrayValue(obj.repair_tickets) ?? []),
      distrust_reasons: stringArray(obj.distrust_reasons) ?? [],
    };
  });
}

function coerceVerdictStatus(value: string | undefined): VerificationVerdict["verdict"] {
  if (value === "pass" || value === "fail" || value === "needs_review") return value;
  return "needs_review";
}

function coerceRepairTickets(values: unknown[]): RepairTicket[] {
  const tickets = values.map((value, index) => {
    const obj = objectValue(value) ?? {};
    return {
      ticket_id: stringValue(obj.ticket_id) ?? `ticket_${index + 1}`,
      hypothesis_id: stringValue(obj.hypothesis_id) ?? "",
      failure_type: coerceFailureType(stringValue(obj.failure_type)),
      failed_check: stringValue(obj.failed_check) ?? "",
      observed_problem: stringValue(obj.observed_problem) ?? stringValue(obj.reason) ?? "",
      repair_action: stringValue(obj.repair_action) ?? "",
      max_attempts_remaining: numberOrDefault(obj.max_attempts_remaining, 0),
    };
  });
  return [...new Map(tickets.map((ticket) => [ticket.ticket_id, ticket])).values()];
}

function coerceFailureType(value: string | undefined): RepairTicket["failure_type"] {
  if (
    value === "grounding_failed" ||
    value === "source_failed" ||
    value === "missing_fact" ||
    value === "invalid_json" ||
    value === "conflict" ||
    value === "low_confidence"
  ) {
    return value;
  }
  return "low_confidence";
}

function coerceDeterminations(values: unknown[] | undefined): Determination[] {
  return (values ?? []).map((value) => {
    const obj = objectValue(value) ?? {};
    const applies = stringValue(obj.applies) ?? stringValue(obj.status);
    return {
      requirement: stringValue(obj.requirement) ?? stringValue(obj.hypothesis_id) ?? "",
      applies: applies === "yes" || applies === "no" || applies === "needs_review" ? applies : "needs_review",
      trigger: stringValue(obj.trigger) ?? "",
      project_fact: stringValue(obj.project_fact) ?? "",
      citation: stringValue(obj.citation) ?? "",
      quote: stringValue(obj.quote) ?? "",
      source_url: stringValue(obj.source_url) ?? "",
      confidence: numberOrDefault(obj.confidence, 0),
      verified: Boolean(obj.verified),
      review_flag: Boolean(obj.review_flag),
      permit_filing: objectValue(obj.permit_filing) as Determination["permit_filing"],
      sds_handoff_refs: coerceArray(obj.sds_handoff_refs),
    };
  });
}

function coerceDeterminationsFromSingularResult(
  determination: JsonObject | undefined,
  verdicts: VerificationVerdict[],
  evidence: EvidenceBundle[],
): Determination[] {
  if (!determination) return [];
  const trusted = new Set(stringArray(determination.trusted_hypotheses) ?? []);
  const needsReview = new Set(stringArray(determination.needs_review_hypotheses) ?? []);
  const hypothesisIds = [...new Set([...trusted, ...needsReview])];
  if (hypothesisIds.length === 0) return [];

  const verdictByHypothesis = new Map(verdicts.map((verdict) => [verdict.hypothesis_id, verdict]));
  const evidenceByHypothesis = new Map(evidence.map((bundle) => [bundle.hypothesis_id, bundle]));
  const reasons = stringArray(determination.reasons) ?? [];

  return hypothesisIds.map((hypothesisId) => {
    const verdict = verdictByHypothesis.get(hypothesisId);
    const bundle = evidenceByHypothesis.get(hypothesisId);
    const source = bundle?.sources[0];
    const extractedClaim = bundle?.extracted_claims[0];
    const reviewFlag = needsReview.has(hypothesisId) || verdict?.verdict === "fail" || verdict?.verdict === "needs_review";

    return {
      requirement: hypothesisId,
      applies: appliesFromResearcherConclusion(bundle?.researcher_conclusion, reviewFlag),
      trigger: extractedClaim?.field || "Python runtime synthesis",
      project_fact: extractedClaim ? `${extractedClaim.field}: ${extractedClaim.value}` : reasons.join("; "),
      citation: source?.source_name ?? "",
      quote: source?.quote ?? "",
      source_url: source?.url ?? "",
      confidence: verdict?.confidence ?? 0,
      verified: trusted.has(hypothesisId) || verdict?.verdict === "pass",
      review_flag: reviewFlag,
      permit_filing: bundle?.permit_filing,
    };
  });
}

function appliesFromResearcherConclusion(conclusion: EvidenceBundle["researcher_conclusion"] | undefined, reviewFlag: boolean): Determination["applies"] {
  if (reviewFlag) return "needs_review";
  if (conclusion === "applies") return "yes";
  if (conclusion === "does_not_apply") return "no";
  return "needs_review";
}

function coerceCoverageStatuses(values: unknown[] | undefined, requests: InformationRequest[]): CoverageFamilyStatus[] {
  const statuses = (values ?? []).flatMap((value, index): CoverageFamilyStatus[] => {
    const obj = objectValue(value) ?? {};
    const family = coerceCoverageFamily(obj.family ?? obj.id);
    if (!family) return [];
    return [{
      id: stringValue(obj.id) ?? `cf-${family}-${index + 1}`,
      family,
      status: coerceCoverageStatus(stringValue(obj.status)),
      reason: stringValue(obj.reason) ?? "",
      project_facts_considered: stringArray(obj.project_facts_considered) ?? [],
      missing_facts: stringArray(obj.missing_facts) ?? [],
    }];
  });

  for (const request of requests) {
    for (const block of request.blocks) {
      const family = coerceCoverageFamily(block);
      if (!family || statuses.some((status) => status.family === family)) continue;
      statuses.push({
        id: `cf-${family}`,
        family,
        status: "blocked_missing_fact",
        reason: request.why_needed,
        project_facts_considered: [],
        missing_facts: [request.field],
      });
    }
  }

  return statuses;
}

function coerceCoverageStatus(value: string | undefined): CoverageFamilyStatus["status"] {
  if (value === "active" || value === "blocked_missing_fact" || value === "out_of_scope" || value === "discovery_candidate") return value;
  return "active";
}

function coerceResearchGraph(
  graphValues: unknown[] | undefined,
  determinations: Determination[],
  evidence: EvidenceBundle[],
  statuses: CoverageFamilyStatus[],
): ResearchHypothesis[] {
  const graph = coerceArray<ResearchHypothesis>(graphValues);
  if (graph.length > 0) return graph;
  const familyFallback = statuses[0]?.family ?? "hazmat";
  return determinations.map((determination, index) => {
    const evidenceBundle = evidence[index];
    return {
      id: evidenceBundle?.hypothesis_id ?? `python-det-${index + 1}`,
      angle_id: `python-angle-${index + 1}`,
      family: familyFallback,
      question: determination.requirement,
      required_facts: [],
      expected_source_type: "agency_guidance",
      success_criteria: [],
      dependencies: [],
    };
  });
}

function coerceEvidenceBundles(values: unknown[] | undefined): EvidenceBundle[] {
  return (values ?? []).map((value) => {
    const obj = objectValue(value) ?? {};
    return {
      hypothesis_id: stringValue(obj.hypothesis_id) ?? "",
      sources: (arrayValue(obj.sources) ?? []).map((source) => {
        const sourceObj = objectValue(source) ?? {};
        return {
          url: stringValue(sourceObj.url) ?? "",
          source_name: stringValue(sourceObj.source_name) ?? stringValue(sourceObj.name) ?? "",
          authority_rank: numberOrDefault(sourceObj.authority_rank, 99),
          fetched_at: stringValue(sourceObj.fetched_at) ?? "",
          content_hash: stringValue(sourceObj.content_hash) ?? "",
          effective_date: stringValue(sourceObj.effective_date) ?? null,
          quote: stringValue(sourceObj.quote) ?? "",
        };
      }),
      extracted_claims: coerceArray(obj.extracted_claims),
      researcher_conclusion: coerceResearcherConclusion(stringValue(obj.researcher_conclusion)),
      uncertainties: stringArray(obj.uncertainties) ?? [],
      permit_filing: objectValue(obj.permit_filing) as EvidenceBundle["permit_filing"],
    };
  });
}

function coerceResearcherConclusion(value: string | undefined): EvidenceBundle["researcher_conclusion"] {
  if (value === "applies" || value === "does_not_apply" || value === "needs_review") return value;
  return "needs_review";
}

function coerceTraceEvents(values: unknown[] | undefined, runId: string): TraceEvent[] {
  return (values ?? []).map((value, index) => {
    const obj = objectValue(value) ?? {};
    const payload = objectValue(obj.payload) ?? {};
    const scope = stringValue(obj.scope);
    const [scopeActor, scopePhase] = scope?.split(":") ?? [];
    const phase = stringValue(obj.phase) ?? scopePhase ?? scopeActor ?? "event";
    const status = coerceTraceStatus(stringValue(obj.status) ?? stringValue(payload.status) ?? scopePhase ?? stringValue(obj.type));
    const artifactIds = [
      stringValue(obj.artifact_id),
      stringValue(payload.artifact_id),
      stringValue(payload.hypothesis_id),
      stringValue(payload.task_id),
      stringValue(payload.raindrop_artifact_id),
    ].filter((item): item is string => Boolean(item));
    return {
      id: stringValue(obj.id) ?? `${runId}-trace-${index + 1}`,
      run_id: stringValue(obj.run_id) ?? runId,
      ts: stringValue(obj.ts) ?? stringValue(obj.created_at) ?? new Date(0).toISOString(),
      actor: stringValue(obj.actor) ?? actorForScope(scopeActor),
      phase,
      status,
      message: stringValue(obj.message) ?? traceMessage(scope, payload, status),
      artifact_id: artifactIds[0],
      artifact_ids: artifactIds.length > 0 ? artifactIds : undefined,
      raindrop_artifact_id: stringValue(obj.raindrop_artifact_id) ?? stringValue(payload.raindrop_artifact_id),
      payload,
    };
  });
}

function coerceTraceStatus(value: string | undefined): TraceEvent["status"] {
  if (value === "queued" || value === "running" || value === "done" || value === "failed" || value === "needs_review" || value === "needs_information") return value;
  if (value === "start") return "running";
  if (value === "complete" || value === "bundle" || value === "verdict" || value === "finish") return "done";
  return "running";
}

function actorForScope(scopeActor: string | undefined): string {
  if (scopeActor === "scope") return "scope_agent";
  if (scopeActor === "plan" || scopeActor === "research" || scopeActor === "run") return "orchestrator";
  if (scopeActor === "verify") return "verifier";
  return scopeActor ?? "python_runtime";
}

function traceMessage(scope: string | undefined, payload: JsonObject, status: TraceEvent["status"]): string {
  const message = stringValue(payload.message) ?? stringValue(payload.reason);
  if (message) return message;
  return scope ? `${scope} ${status}` : status;
}

function coerceReportMarkdown(pythonRun: JsonObject, result: JsonObject | undefined): string {
  const report = objectValue(result?.report);
  const summary = stringValue(report?.summary);
  return (
    stringValue(pythonRun.report_markdown) ??
    stringValue(result?.report_markdown) ??
    stringValue(report?.markdown) ??
    (summary ? `## Research Report\n\n${summary}` : "")
  );
}

function collectDistrustReasons(result: JsonObject | undefined, verdicts: VerificationVerdict[]): string[] {
  const determination = objectValue(result?.determination);
  return [
    ...(stringArray(determination?.reasons) ?? []),
    ...verdicts.flatMap((verdict) => verdict.distrust_reasons ?? []),
  ];
}

function coerceCoverageFamily(value: unknown): CoverageFamily | null {
  const text = stringValue(value)?.toLowerCase().replaceAll("_", "-");
  if (!text) return null;
  const exact = COVERAGE_FAMILIES.find((family) => text === family || text === family.replace("_", "-"));
  if (exact) return exact;
  const alias = COVERAGE_FAMILY_ALIASES.find(([, aliases]) => aliases.some((candidate) => text === candidate || text.includes(candidate)))?.[0];
  if (alias) return alias;
  return [...COVERAGE_FAMILIES]
    .sort((left, right) => right.length - left.length)
    .find((family) => text.includes(family) || text.includes(family.replace("_", "-"))) ?? null;
}

function coerceArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? value as T[] : [];
}

function objectValue(value: unknown): JsonObject | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value as JsonObject : undefined;
}

function arrayValue(value: unknown): unknown[] | undefined {
  return Array.isArray(value) ? value : undefined;
}

function stringValue(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function stringArray(value: unknown): string[] | undefined {
  return Array.isArray(value) ? value.map((item) => String(item)) : undefined;
}

function numberOrDefault(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function booleanOrNull(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}
