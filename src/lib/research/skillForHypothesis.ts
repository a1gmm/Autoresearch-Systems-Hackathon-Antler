// Maps each research hypothesis to the LAW-CODE skill the researcher reads as
// just-in-time orienting context (src/lib/research/skills/<id>/SKILL.md).
//
// Skills are per law/rule (one skill = one program in programRegistry.ts), NOT
// per coverage family — so a researcher orients on the specific rule it must
// fetch and quote (e.g. SCAQMD Rule 219 vs Rule 222), not a lumped family doc.
//
// Keep in sync with programRegistry.ts: every hypothesis id MUST have an entry
// here pointing at a real skill dir. registrySkillsParity.test.ts enforces this.

export const SKILL_FOR_HYPOTHESIS: Record<string, string> = {
  // SCAQMD air — one skill per rule
  "H-AIR-201": "scaqmd-permit-to-construct",
  "H-AIR-VOC": "scaqmd-permit-to-construct",
  "H-AIR-219": "scaqmd-rule-219-exemption",
  "H-AIR-222": "scaqmd-rule-222-registration",
  // stormwater — one skill per permit
  "H-STORM-IGP": "ca-industrial-general-permit",
  "H-STORM-CGP": "ca-construction-general-permit",
  // hazmat
  "H-HAZMAT-HMBP": "ca-hmbp",
  // hazardous waste
  "H-WASTE-GENERATOR": "epa-hazwaste-generator",
  // wastewater pretreatment
  "H-WASTEWATER-PRETREATMENT": "epa-pretreatment",
};

// Returns the skill id for a hypothesis id, or null if none is mapped.
export function skillForHypothesis(id: string): string | null {
  return SKILL_FOR_HYPOTHESIS[id] ?? null;
}
