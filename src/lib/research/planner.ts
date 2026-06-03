import type {
  CoverageFamily,
  CoverageFamilyStatus,
  RegulatoryAngle,
  ResearchHypothesis,
  ResearchTask,
  ScopePack
} from "./types";
import { blockedToolIdsForRole, researchWorkerToolIds } from "./toolCatalog";
import { PROGRAM_REGISTRY, type ProgramRegistryEntry } from "./programRegistry";
import { jurisdictionContextFor } from "./jurisdictionResolve";

// The planner generates a hypothesis TASK LIST from the program registry — the
// single source of truth — instead of a hardcoded family array or a fixed pool
// of angles. For each registry program whose triggeredBy(scope) fires (or whose
// family an SDS review flagged), every hypothesis on that program becomes a
// research task. Adding a program to the registry adds it to the plan; nothing
// here is hardcoded per family or per hypothesis id.
export function planResearch(scope: ScopePack, sdsActiveFamilies: ReadonlySet<CoverageFamily> = new Set()) {
  // Families come from the registry, not a hardcoded list.
  const families = [...new Set(PROGRAM_REGISTRY.map((p) => p.family))];
  const coverage_family_statuses = families.map((family) =>
    coverageStatusFor(family, scope, sdsActiveFamilies.has(family))
  );

  const activeFamilies = new Set(
    coverage_family_statuses.filter((s) => s.status !== "out_of_scope").map((s) => s.family)
  );

  // A program is in-scope when its own trigger fires OR an SDS flagged its family
  // (and the family wasn't ruled out_of_scope). One regulatory angle per program.
  const activePrograms = PROGRAM_REGISTRY.filter(
    (program) =>
      activeFamilies.has(program.family) && (program.triggeredBy(scope) || sdsActiveFamilies.has(program.family))
  );

  const familyStatusBy = new Map(coverage_family_statuses.map((s) => [s.family, s]));
  const regulatory_angles: RegulatoryAngle[] = activePrograms.map((program) =>
    angleForProgram(program, familyStatusBy.get(program.family))
  );

  // Hypotheses are the task list: every hypothesis of every active program.
  const research_graph: ResearchHypothesis[] = activePrograms.flatMap((program) =>
    program.hypotheses.map((h) => hypothesisFromRegistry(program, h, familyStatusBy.get(program.family)))
  );
  // Resolve the local jurisdiction once and hand every research task the same
  // orienting context (controlling authorities + local skill bodies + gaps).
  const jurisdiction_context = jurisdictionContextFor(scope.facility);
  const research_tasks = research_graph.map((h) => taskForHypothesis(h, jurisdiction_context));

  return { coverage_family_statuses, regulatory_angles, research_graph, research_tasks };
}

// Per-family in-scope / blocked / out-of-scope status. This is fact-driven (not a
// hardcoded pool): each family reads the scope facts its programs depend on and
// reports missing facts that block a confident determination.
function coverageStatusFor(family: CoverageFamily, scope: ScopePack, sdsFlagged: boolean): CoverageFamilyStatus {
  const equipmentKinds = scope.project_change.equipment.map((item) => item.kind);
  const hasChemicals = scope.project_change.chemicals.length > 0;
  const hasWaste = scope.project_change.waste_streams.length > 0;
  const disturbance = scope.project_change.disturbance_acres;
  const id = `CF-${family.toUpperCase()}`;

  if (family === "air") {
    const equipmentActive = scope.project_change.equipment.length > 0;
    const active = equipmentActive || sdsFlagged;
    return {
      id,
      family,
      status: active ? "active" : "out_of_scope",
      reason: equipmentActive
        ? "Project adds equipment that may emit air contaminants."
        : sdsFlagged
          ? "SDS review flagged VOC or air-emissions relevance; air permit applicability requires review."
          : "No equipment added that could emit air contaminants.",
      project_facts_considered: sdsFlagged ? [...equipmentKinds, "sds:voc_air_emissions_review"] : equipmentKinds,
      missing_facts: []
    };
  }

  if (family === "stormwater") {
    const missingCode = !scope.facility.sic && !scope.facility.naics && disturbance === null;
    return {
      id,
      family,
      status: missingCode ? "blocked_missing_fact" : "active",
      reason: missingCode
        ? "SIC/NAICS and disturbance acreage are missing."
        : "Industrial activity codes or construction acreage require stormwater review.",
      project_facts_considered: [`sic=${scope.facility.sic}`, `naics=${scope.facility.naics}`, `acres=${disturbance}`],
      missing_facts: missingCode ? ["facility.naics_or_sic", "project_change.disturbance_acres"] : []
    };
  }

  if (family === "hazmat") {
    const missingQuantity = hasChemicals && scope.project_change.chemicals.some((chemical) => chemical.quantity === null);
    return {
      id,
      family,
      status: !hasChemicals ? (sdsFlagged ? "active" : "out_of_scope") : missingQuantity ? "blocked_missing_fact" : "active",
      reason: hasChemicals
        ? "Project includes hazardous material storage."
        : sdsFlagged
          ? "SDS review flagged hazardous material content; HMBP applicability requires review."
          : "No hazardous materials indicated in intake.",
      project_facts_considered: scope.project_change.chemicals.map((chemical) => `${chemical.name}:${chemical.quantity ?? "missing"} ${chemical.unit ?? ""}`),
      missing_facts: missingQuantity ? ["chemicals.quantity", "chemicals.unit"] : []
    };
  }

  if (family === "waste") {
    return {
      id,
      family,
      status: hasWaste || sdsFlagged ? "active" : "out_of_scope",
      reason: hasWaste
        ? "Project identifies waste streams that need generator-status review."
        : sdsFlagged
          ? "SDS review flagged hazardous waste relevance; generator-status review required."
          : "No waste stream indicated.",
      project_facts_considered: scope.project_change.waste_streams.map((stream) => `${stream.description}:${stream.kg_per_month ?? "missing"} kg/month`),
      missing_facts: scope.project_change.waste_streams.some((stream) => stream.kg_per_month === null)
        ? ["waste_streams.kg_per_month"]
        : []
    };
  }

  if (family === "wastewater") {
    const discharge = scope.project_change.process_discharge;
    return {
      id,
      family,
      status: discharge === null ? (sdsFlagged ? "active" : "blocked_missing_fact") : discharge ? "active" : sdsFlagged ? "active" : "out_of_scope",
      reason:
        discharge === null
          ? sdsFlagged
            ? "SDS review flagged spill/stormwater containment relevance; pretreatment review required."
            : "Process discharge status is missing."
          : discharge
            ? "Project may discharge process wastewater."
            : "No process wastewater discharge indicated.",
      project_facts_considered: [`process_discharge=${discharge}`],
      missing_facts: discharge === null ? ["project_change.process_discharge"] : []
    };
  }

  // Any future family in the registry with no special fact logic yet: active when
  // its programs trigger or an SDS flags it; otherwise out_of_scope. Fail-open to
  // active (a new family should be investigated, not silently skipped).
  return {
    id,
    family,
    status: sdsFlagged ? "active" : "active",
    reason: "Registry program applies to this family; investigate.",
    project_facts_considered: [],
    missing_facts: []
  };
}

function angleForProgram(program: ProgramRegistryEntry, status: CoverageFamilyStatus | undefined): RegulatoryAngle {
  return {
    id: `A-${program.id}`,
    family: program.family,
    label: program.name,
    reason: program.what_it_does,
    triggering_facts: status?.project_facts_considered ?? [],
    status: status?.status ?? "active"
  };
}

function hypothesisFromRegistry(
  program: ProgramRegistryEntry,
  h: ProgramRegistryEntry["hypotheses"][number],
  status: CoverageFamilyStatus | undefined
): ResearchHypothesis {
  return {
    id: h.id,
    angle_id: `A-${program.id}`,
    family: program.family,
    question: h.question,
    claim_to_test: h.claim_to_test,
    required_facts: status?.project_facts_considered ?? [],
    expected_source_type: "regulation",
    success_criteria: [
      "official or high-authority source",
      "quote contains trigger, threshold, exemption, or blocker",
      "predicate evaluation is reproducible"
    ],
    dependencies: []
  };
}

export function taskForHypothesis(hypothesis: ResearchHypothesis, jurisdiction_context?: string): ResearchTask {
  return {
    task_id: `T-${hypothesis.id.slice(2)}`,
    hypothesis_id: hypothesis.id,
    assigned_agent: `${hypothesis.family}_researcher`,
    allowed_tools: researchWorkerToolIds(),
    blocked_tools: blockedToolIdsForRole("researcher"),
    budget: {
      // Headroom for genuine investigation: discover via web_search, fetch + corroborate
      // across multiple authorities, and ground — not just fetch-one-known-url.
      max_sources: 5,
      max_runtime_seconds: 90,
      max_model_calls: 8
    },
    ...(jurisdiction_context ? { jurisdiction_context } : {})
  };
}
