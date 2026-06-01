// Single source of truth for permit programs. The verifier owns this list;
// completeness.ts re-derives the expected set from it. Family skills are
// projections of it (see registrySkillsParity.test.ts).
import type { CoverageFamily, ScopePack } from "./types";

// One testable claim the researcher investigates for a program. The registry is
// the single source of truth: the planner generates its hypothesis task list
// from these, instead of a hardcoded angle pool.
export type ProgramHypothesis = {
  id: string;
  question: string;
  claim_to_test: string;
};

export type ProgramRegistryEntry = {
  id: string;
  family: CoverageFamily;
  name: string;
  what_it_does: string;
  jurisdiction: string;
  authority_source_url: string;
  authority_rank: number;
  // The hypotheses (testable claims) that investigate this program. The planner
  // emits one research task per hypothesis when the program is triggered.
  hypotheses: ProgramHypothesis[];
  // Deterministic: does this project's scope make this program potentially applicable?
  triggeredBy: (scope: ScopePack) => boolean;
};

const hasEquipment = (s: ScopePack) => s.project_change.equipment.length > 0;
const hasChemicals = (s: ScopePack) => s.project_change.chemicals.length > 0;
const hasWaste = (s: ScopePack) => s.project_change.waste_streams.length > 0;
const hasCodeOrAcres = (s: ScopePack) =>
  !!s.facility.sic || !!s.facility.naics || s.project_change.disturbance_acres !== null;
const dischargePossible = (s: ScopePack) => s.project_change.process_discharge !== false;

export const PROGRAM_REGISTRY: ProgramRegistryEntry[] = [
  {
    id: "scaqmd-permit-to-construct",
    family: "air",
    name: "SCAQMD Permit to Construct (Rule 201)",
    what_it_does: "Authorizes installing/modifying equipment that may emit air contaminants.",
    jurisdiction: "SCAQMD",
    authority_source_url: "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-201.pdf",
    authority_rank: 1,
    hypotheses: [
      { id: "H-AIR-201", question: "Does the new equipment require an SCAQMD Permit to Construct?", claim_to_test: "SCAQMD Permit to Construct may apply before installing emitting equipment." },
      { id: "H-AIR-VOC", question: "Do solvent VOC emissions require additional review?", claim_to_test: "Solvent use may create VOC-related review needs." },
    ],
    triggeredBy: hasEquipment,
  },
  {
    id: "scaqmd-rule-219-exemption",
    family: "air",
    name: "SCAQMD Rule 219 exemption",
    what_it_does: "Exempts listed equipment from written permit requirements if conditions are met.",
    jurisdiction: "SCAQMD",
    authority_source_url: "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-219.pdf",
    authority_rank: 1,
    hypotheses: [
      { id: "H-AIR-219", question: "Is Rule 219 exemption available?", claim_to_test: "Rule 219 may exempt listed equipment if conditions are satisfied." },
    ],
    triggeredBy: hasEquipment,
  },
  {
    id: "scaqmd-rule-222-registration",
    family: "air",
    name: "SCAQMD Rule 222 registration",
    what_it_does: "Registration path for specified equipment categories instead of a full permit.",
    jurisdiction: "SCAQMD",
    authority_source_url: "https://www.aqmd.gov/docs/default-source/rule-book/reg-ii/rule-222.pdf",
    authority_rank: 1,
    hypotheses: [
      { id: "H-AIR-222", question: "Does Rule 222 registration apply instead?", claim_to_test: "Rule 222 registration may apply to specified equipment categories." },
    ],
    triggeredBy: hasEquipment,
  },
  {
    id: "ca-industrial-general-permit",
    family: "stormwater",
    name: "California Industrial General Permit (IGP)",
    what_it_does: "Stormwater coverage triggered by industrial activity SIC/NAICS codes.",
    jurisdiction: "California Water Boards",
    authority_source_url: "https://www.waterboards.ca.gov/water_issues/programs/stormwater/industrial.html",
    authority_rank: 1,
    hypotheses: [
      { id: "H-STORM-IGP", question: "Does SIC/NAICS trigger Industrial General Permit coverage?", claim_to_test: "SIC/NAICS may trigger California Industrial General Permit coverage." },
    ],
    triggeredBy: hasCodeOrAcres,
  },
  {
    id: "ca-construction-general-permit",
    family: "stormwater",
    name: "California Construction General Permit (CGP)",
    what_it_does: "Stormwater coverage for construction disturbing one or more acres.",
    jurisdiction: "California Water Boards",
    authority_source_url: "https://www.waterboards.ca.gov/water_issues/programs/stormwater/construction.html",
    authority_rank: 1,
    hypotheses: [
      { id: "H-STORM-CGP", question: "Does construction disturb one or more acres?", claim_to_test: "Construction disturbance at or above one acre may require construction stormwater permit coverage." },
    ],
    triggeredBy: hasCodeOrAcres,
  },
  {
    id: "ca-hmbp",
    family: "hazmat",
    name: "California Hazardous Materials Business Plan (HMBP)",
    what_it_does: "Reporting plan triggered by hazardous material quantities at or above thresholds.",
    jurisdiction: "CalEPA / local CUPA",
    authority_source_url: "https://calepa.ca.gov/cupa/hazardous-materials-business-plan/",
    authority_rank: 1,
    hypotheses: [
      { id: "H-HAZMAT-HMBP", question: "Does hazardous material quantity exceed HMBP thresholds?", claim_to_test: "Hazardous material quantities at or above HMBP thresholds require a business plan." },
    ],
    triggeredBy: hasChemicals,
  },
  {
    id: "epa-hazwaste-generator",
    family: "waste",
    name: "EPA Hazardous Waste Generator Category",
    what_it_does: "Generator status (VSQG/SQG/LQG) based on monthly hazardous waste quantity.",
    jurisdiction: "US EPA / CA DTSC",
    authority_source_url: "https://www.epa.gov/hwgenerators/categories-hazardous-waste-generators",
    authority_rank: 1,
    hypotheses: [
      { id: "H-WASTE-GENERATOR", question: "Does waste generation change hazardous waste generator status?", claim_to_test: "Spent solvent or process waste may affect generator category." },
    ],
    triggeredBy: hasWaste,
  },
  {
    id: "epa-pretreatment",
    family: "wastewater",
    name: "EPA National Pretreatment Program",
    what_it_does: "Pretreatment requirements for industrial process wastewater discharges.",
    jurisdiction: "US EPA",
    authority_source_url: "https://www.epa.gov/npdes/national-pretreatment-program",
    authority_rank: 1,
    hypotheses: [
      { id: "H-WASTEWATER-PRETREATMENT", question: "Does process wastewater discharge require pretreatment review?", claim_to_test: "Industrial process wastewater may require pretreatment review." },
    ],
    triggeredBy: dischargePossible,
  },
];

export function allPrograms(): ProgramRegistryEntry[] {
  return PROGRAM_REGISTRY;
}

export function programsForFamily(family: CoverageFamily): ProgramRegistryEntry[] {
  return PROGRAM_REGISTRY.filter((p) => p.family === family);
}
