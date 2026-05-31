import type { SdsReview } from "@/lib/sds/types";
import type { ResearchRunInput, ScopePack } from "./types";
import { seededComplexScope, seededConstructionScope, seededMissingFactsScope } from "./fixtures/scenarios";

export function createRunId() {
  return `run_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

export function parseScope(input: ResearchRunInput, runId: string): ScopePack {
  const description = input.project_description.trim();
  const normalized = description.toLowerCase();

  if (normalized.includes("missing") || normalized.includes("omit") || normalized.includes("unknown")) {
    return seededMissingFactsScope(runId, description);
  }

  if (normalized.includes("1.2 acre") || normalized.includes("construction")) {
    return seededConstructionScope(runId, description);
  }

  return seededComplexScope(runId, description);
}

export function projectFacts(scope: ScopePack): Record<string, unknown> {
  const sdsHandoffAssumptions = scope.assumptions.filter((assumption) =>
    assumption.claim.startsWith("SDS candidate fact:")
  );

  return {
    address: scope.facility.address,
    naics: scope.facility.naics,
    sic: scope.facility.sic,
    equipment: scope.project_change.equipment,
    chemicals: scope.project_change.chemicals,
    waste_streams: scope.project_change.waste_streams,
    disturbance_acres: scope.project_change.disturbance_acres,
    process_discharge: scope.project_change.process_discharge,
    missing_facts: scope.missing_facts,
    sds_handoff_assumptions: sdsHandoffAssumptions
  };
}

export function applySdsHandoffToScope(scope: ScopePack, sdsReviews: SdsReview[]): ScopePack {
  const permitHandoffFacts = sdsReviews.flatMap((review) =>
    review.permit_handoff_facts.filter((fact) => fact.review_flag)
  );

  if (permitHandoffFacts.length === 0) {
    return scope;
  }

  const chemicals = scope.project_change.chemicals.map((chemical) => ({ ...chemical }));
  const wasteStreams = scope.project_change.waste_streams.map((stream) => ({ ...stream }));
  const assumptions = scope.assumptions.map((assumption) => ({ ...assumption }));
  const missingFacts = scope.missing_facts.map((missingFact) => ({
    ...missingFact,
    blocks: [...missingFact.blocks]
  }));

  if (permitHandoffFacts.some(isHazardousMaterialFact) && chemicals.length === 0) {
    chemicals.push({
      name: "SDS candidate hazardous material",
      quantity: null,
      unit: null,
      hazard: "SDS candidate"
    });
    addMissingFactOnce(missingFacts, {
      field: "chemicals.quantity",
      why_needed: "SDS handoff indicates hazardous material review, but quantity and units still require confirmation.",
      blocks: ["hmbp_threshold"]
    });
  }

  if (permitHandoffFacts.some(isHazardousWasteFact) && wasteStreams.length === 0) {
    wasteStreams.push({
      description: "SDS candidate hazardous waste stream",
      kg_per_month: null
    });
    addMissingFactOnce(missingFacts, {
      field: "waste_streams.kg_per_month",
      why_needed: "SDS handoff indicates hazardous waste review, but monthly waste generation still requires confirmation.",
      blocks: ["hazardous_waste_generator_status"]
    });
  }

  for (const fact of permitHandoffFacts) {
    assumptions.push({
      claim: `SDS candidate fact: ${fact.field}=${String(fact.value)}`,
      basis: `Section ${fact.source_section}: ${fact.quote}`,
      confidence: fact.confidence
    });
  }

  return {
    ...scope,
    project_change: {
      ...scope.project_change,
      chemicals,
      waste_streams: wasteStreams
    },
    missing_facts: missingFacts,
    assumptions
  };
}

function addMissingFactOnce(
  missingFacts: ScopePack["missing_facts"],
  missingFact: ScopePack["missing_facts"][number]
) {
  if (missingFacts.some((candidate) => candidate.field === missingFact.field)) {
    return;
  }

  missingFacts.push(missingFact);
}

function isHazardousMaterialFact(fact: SdsReview["permit_handoff_facts"][number]) {
  return [
    "hazardous_material_inventory_review",
    "flammable_liquid_storage_review",
    "incompatible_storage_review",
    "california_ehs_review"
  ].includes(fact.field);
}

function isHazardousWasteFact(fact: SdsReview["permit_handoff_facts"][number]) {
  return fact.field === "hazardous_waste_review";
}
