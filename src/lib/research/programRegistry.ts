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

  // --- Additional verified California state programs (deep-researched against
  // ca.gov / CalEPA / Water Boards / DTSC / CDPH / CARB / OEHHA / leginfo).
  // Triggers are recall-maximizing on the facts ScopePack captures today
  // (chemicals/equipment/discharge); the agent + verifier prune to needs_review
  // rather than guess. Programs whose true trigger needs facts we don't model
  // yet (tanks, petroleum gallons, employee count) are noted in their claim. ---
  {
    id: "ca-ust-program",
    family: "hazmat",
    name: "Underground Storage Tank (UST) Program",
    what_it_does: "Leak prevention, monitoring, and permitting for tanks storing hazardous substances substantially beneath ground.",
    jurisdiction: "State Water Board; administered by the local CUPA",
    authority_source_url: "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=HSC&sectionNum=25281.",
    authority_rank: 1,
    hypotheses: [
      { id: "H-HAZMAT-UST", question: "Does the facility have a regulated underground storage tank?", claim_to_test: "Any qualifying underground tank storing a hazardous substance is regulated (farm/residential <=1,100 gal exemptions aside)." },
    ],
    triggeredBy: hasChemicals,
  },
  {
    id: "ca-apsa-spcc",
    family: "hazmat",
    name: "Aboveground Petroleum Storage Act (APSA)",
    what_it_does: "Requires an SPCC plan and CUPA registration for aboveground petroleum storage.",
    jurisdiction: "CAL FIRE Office of the State Fire Marshal; administered by the local CUPA",
    authority_source_url: "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=HSC&sectionNum=25270.",
    authority_rank: 1,
    hypotheses: [
      { id: "H-HAZMAT-APSA", question: "Does aggregate aboveground petroleum storage reach the APSA threshold?", claim_to_test: "Aggregate aboveground petroleum capacity of 1,320 gallons or more (containers >=55 gal) triggers APSA." },
    ],
    triggeredBy: hasChemicals,
  },
  {
    id: "ca-calarp-program",
    family: "hazmat",
    name: "California Accidental Release Prevention (CalARP)",
    what_it_does: "Requires a Risk Management Plan for processes holding a regulated substance above its threshold quantity.",
    jurisdiction: "CalEPA; administered by the local UPA/CUPA",
    authority_source_url: "https://calepa.ca.gov/wp-content/uploads/2024/08/California-Code-of-Regulations-Title-19-Division-5-Chapter-2-%E2%80%93-California-Accidental-Release-Prevention.pdf",
    authority_rank: 1,
    hypotheses: [
      { id: "H-HAZMAT-CALARP", question: "Does a process hold a regulated substance above its CalARP threshold quantity?", claim_to_test: "Per-substance threshold quantities in 19 CCR 5130.6 Tables 1-3 determine RMP applicability." },
    ],
    triggeredBy: hasChemicals,
  },
  {
    id: "ca-ab2588-hot-spots",
    family: "air",
    name: "AB 2588 Air Toxics \"Hot Spots\"",
    what_it_does: "Toxic air emissions inventory, risk assessment, and public notification for stationary sources.",
    jurisdiction: "CARB statewide guidelines; administered by the local air district",
    authority_source_url: "https://ww2.arb.ca.gov/our-work/programs/ab-2588-air-toxics-hot-spots",
    authority_rank: 1,
    hypotheses: [
      { id: "H-AIR-AB2588", question: "Is the facility subject to AB 2588 air-toxics reporting?", claim_to_test: "Stationary sources emitting Appendix A substances report per district-defined inclusion criteria (no single statewide tonnage)." },
    ],
    triggeredBy: hasEquipment,
  },
  {
    id: "ca-prop-65",
    family: "hazmat",
    name: "Proposition 65",
    what_it_does: "Warning and discharge requirements for chemicals on the OEHHA Prop 65 list.",
    jurisdiction: "OEHHA lists; enforced by the AG, DAs, and private litigants",
    authority_source_url: "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=HSC&sectionNum=25249.6.",
    authority_rank: 1,
    hypotheses: [
      { id: "H-HAZMAT-PROP65", question: "Does the facility expose people to a Prop 65-listed chemical above safe-harbor levels?", claim_to_test: "Businesses with 10+ employees must warn before exposing individuals to a listed chemical above its safe-harbor level." },
    ],
    triggeredBy: hasChemicals,
  },
  {
    id: "ca-title22-hazwaste",
    family: "waste",
    name: "California Hazardous Waste (Title 22, non-RCRA)",
    what_it_does: "California-only hazardous wastes broader than federal RCRA (STLC/TTLC criteria).",
    jurisdiction: "DTSC; administered by the local CUPA",
    authority_source_url: "https://dtsc.ca.gov/non-rcra-hazardous-wastes/",
    authority_rank: 1,
    hypotheses: [
      { id: "H-WASTE-CA-TITLE22", question: "Is the waste a California-only (non-RCRA) hazardous waste?", claim_to_test: "A waste may be California hazardous under 22 CCR 66261.24 (STLC/TTLC) even if not federally hazardous." },
    ],
    triggeredBy: hasWaste,
  },
  {
    id: "ca-medical-waste",
    family: "waste",
    name: "Medical Waste Management Act",
    what_it_does: "Registration and management of medical/biohazardous and sharps waste.",
    jurisdiction: "CDPH; enforced by the local enforcement agency",
    authority_source_url: "https://leginfo.legislature.ca.gov/faces/codes_displaySection.xhtml?lawCode=HSC&sectionNum=117600.",
    authority_rank: 1,
    hypotheses: [
      { id: "H-WASTE-MEDICAL", question: "Does the facility generate regulated medical waste?", claim_to_test: "Generating 200 lb/month or more of medical waste makes a facility a Large Quantity Generator requiring registration and a management plan." },
    ],
    triggeredBy: hasWaste,
  },
  {
    id: "ca-universal-waste",
    family: "waste",
    name: "Universal Waste (batteries, lamps, e-waste)",
    what_it_does: "Streamlined management of universal wastes (batteries, lamps, electronics, mercury devices).",
    jurisdiction: "DTSC; administered by the local CUPA",
    authority_source_url: "https://dtsc.ca.gov/requirements-for-handlers-and-or-recyclers/",
    authority_rank: 1,
    hypotheses: [
      { id: "H-WASTE-UNIVERSAL", question: "Does the facility accumulate universal waste?", claim_to_test: "Batteries, lamps, electronic devices, and mercury devices are managed under universal-waste handler standards (22 CCR 66273)." },
    ],
    triggeredBy: hasWaste,
  },
  {
    id: "ca-title-v-permit",
    family: "air",
    name: "Federal Title V Operating Permit (CA air districts)",
    what_it_does: "Consolidated operating permit for major stationary sources, issued by CA air districts.",
    jurisdiction: "US EPA delegated to the local air district",
    authority_source_url: "https://ww2.arb.ca.gov/our-work/programs/federal-clean-air-act-title-v-operating-permits/fcaa-title-v-overview",
    authority_rank: 1,
    hypotheses: [
      { id: "H-AIR-TITLE-V", question: "Is the facility a major source requiring a Title V operating permit?", claim_to_test: "Potential to emit >=100 tpy of a regulated pollutant (lower in nonattainment; 10/25 tpy HAP) makes a source a Title V major source." },
    ],
    triggeredBy: hasEquipment,
  },
  {
    id: "ca-wdr-npdes",
    family: "wastewater",
    name: "NPDES Individual Permit / Waste Discharge Requirements (WDRs)",
    what_it_does: "Regional Water Board permit for process wastewater discharged to surface water or land, not covered by the IGP or POTW pretreatment.",
    jurisdiction: "Regional Water Quality Control Board (one of 9)",
    authority_source_url: "https://www.waterboards.ca.gov/water_issues/programs/waste_discharge_requirements/",
    authority_rank: 1,
    hypotheses: [
      { id: "H-WASTEWATER-WDR", question: "Does the discharge require an individual NPDES permit or WDRs?", claim_to_test: "Discharge of waste to waters of the state/US may require WDRs (Porter-Cologne, Water Code 13260) or an individual NPDES permit." },
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
