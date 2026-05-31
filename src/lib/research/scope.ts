import type { SdsReview } from "@/lib/sds/types";
import type { ResearchRunInput, ScopePack } from "./types";
import { seededComplexScope, seededConstructionScope, seededMissingFactsScope } from "./fixtures/scenarios";
import { isLiveMode } from "./config";

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

// Fail-closed ScopePack: no facts extracted, every decision-relevant family
// blocked on a missing fact so the planner cannot guess applicability. Used when
// the live LLM extraction is unavailable or its output is unusable.
export function emptyScope(runId: string, description: string): ScopePack {
  return {
    run_id: runId,
    facility: {
      address: "Unknown facility",
      jurisdiction_stack: [],
      naics: null,
      sic: null,
    },
    project_change: {
      description: description || "Project description unavailable.",
      equipment: [],
      chemicals: [],
      waste_streams: [],
      disturbance_acres: null,
      process_discharge: null,
    },
    missing_facts: [
      {
        field: "scope.extraction",
        why_needed:
          "Scope extraction was unavailable; no project facts could be derived, so every coverage family fails closed to human review.",
        blocks: [
          "air",
          "industrial_stormwater",
          "hmbp_threshold",
          "hazardous_waste_generator_status",
          "wastewater_pretreatment",
        ],
      },
    ],
    assumptions: [],
  };
}

// Injectable LLM call: takes the project description, returns the model's raw
// JSON string. Kept as a parameter so parseScopeLive is unit-testable without a
// network or API key (see scopeLive.test.ts).
export type ScopeLlmFn = (description: string) => Promise<string>;

// Live scope extraction. Runs the injected llmFn, parses its JSON into a typed
// ScopePack, and fails closed to emptyScope on any error (no key, thrown call,
// unparseable output, or shape mismatch). Never invents values.
export async function parseScopeLive(
  input: ResearchRunInput,
  runId: string,
  llmFn: ScopeLlmFn
): Promise<ScopePack> {
  const description = input.project_description.trim();
  try {
    const raw = await llmFn(description);
    const parsed = JSON.parse(raw) as Partial<ScopePack>;
    return coerceScope(parsed, runId, description);
  } catch {
    return emptyScope(runId, description);
  }
}

// Mode-aware entry point used by run.ts. In fixture mode (the default) this is
// the deterministic keyword parser — no network, reproducible. In a live mode it
// runs the injected llmFn and fails closed to emptyScope if it cannot extract.
export async function resolveScope(
  input: ResearchRunInput,
  runId: string,
  llmFn: ScopeLlmFn = openAiScopeLlmFn
): Promise<ScopePack> {
  if (!isLiveMode()) {
    return parseScope(input, runId);
  }
  return parseScopeLive(input, runId, llmFn);
}

const SCOPE_SYSTEM_PROMPT = [
  "You extract structured EHS permitting facts from a free-text project description.",
  "Return ONLY a JSON object matching this shape:",
  '{"facility":{"address":string,"jurisdiction_stack":string[],"naics":string|null,"sic":string|null},',
  '"project_change":{"description":string,"equipment":[{"kind":string,"description":string}],',
  '"chemicals":[{"name":string,"quantity":number|null,"unit":string|null,"hazard":string}],',
  '"waste_streams":[{"description":string,"kg_per_month":number|null}],',
  '"disturbance_acres":number|null,"process_discharge":boolean|null},',
  '"missing_facts":[{"field":string,"why_needed":string,"blocks":string[]}],"assumptions":[]}',
  "Never invent values. If a decision-relevant fact is absent, set it null and add a missing_facts entry.",
].join(" ");

// Production llmFn: a real OpenAI call. Throws when no key is set so resolveScope
// fails closed to emptyScope. Mirrors the client/model pattern in the intake route.
export const openAiScopeLlmFn: ScopeLlmFn = async (description) => {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY unset; scope extraction unavailable");
  }
  const { default: OpenAI } = await import("openai");
  const client = new OpenAI({ apiKey });
  const model = process.env.OPENAI_INTAKE_MODEL ?? "gpt-4o-mini";
  const completion = await client.chat.completions.create({
    model,
    messages: [
      { role: "system", content: SCOPE_SYSTEM_PROMPT },
      { role: "user", content: description },
    ],
    response_format: { type: "json_object" },
    max_tokens: 1200,
  });
  return completion.choices[0]?.message?.content ?? "";
};

// Validate + normalize an untrusted parsed object into a ScopePack. Throws on a
// shape that cannot represent extracted facts, so parseScopeLive fails closed.
function coerceScope(parsed: Partial<ScopePack>, runId: string, description: string): ScopePack {
  if (!parsed || typeof parsed !== "object" || !parsed.facility || !parsed.project_change) {
    throw new Error("scope extraction missing required sections");
  }

  const facility = parsed.facility;
  const change = parsed.project_change;

  return {
    run_id: runId,
    facility: {
      address: typeof facility.address === "string" ? facility.address : "Unknown facility",
      jurisdiction_stack: Array.isArray(facility.jurisdiction_stack)
        ? facility.jurisdiction_stack.filter((j): j is string => typeof j === "string")
        : [],
      naics: typeof facility.naics === "string" ? facility.naics : null,
      sic: typeof facility.sic === "string" ? facility.sic : null,
    },
    project_change: {
      description: typeof change.description === "string" ? change.description : description,
      equipment: Array.isArray(change.equipment) ? change.equipment : [],
      chemicals: Array.isArray(change.chemicals) ? change.chemicals : [],
      waste_streams: Array.isArray(change.waste_streams) ? change.waste_streams : [],
      disturbance_acres: typeof change.disturbance_acres === "number" ? change.disturbance_acres : null,
      process_discharge: typeof change.process_discharge === "boolean" ? change.process_discharge : null,
    },
    missing_facts: Array.isArray(parsed.missing_facts) ? parsed.missing_facts : [],
    assumptions: Array.isArray(parsed.assumptions) ? parsed.assumptions : [],
  };
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
    review.permit_handoff_facts.filter((fact) => fact.review_flag && fact.value === true)
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
    "incompatible_storage_review"
  ].includes(fact.field);
}

function isHazardousWasteFact(fact: SdsReview["permit_handoff_facts"][number]) {
  return fact.field === "hazardous_waste_review";
}
