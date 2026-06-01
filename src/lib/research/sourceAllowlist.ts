// Host allowlist for EHS research evidence. A researcher agent may only treat a
// fetched page as authoritative evidence if its host is on this list. The hosts
// are derived from the exact authoritative source URLs cited in the skills
// library (src/lib/research/skills/<id>/SKILL.md) and mirrored in
// src/lib/research/modal/worker.py:
//   - www.aqmd.gov            SCAQMD Rules 201 / 219 / 222 (air)
//   - www.waterboards.ca.gov  CA Construction + Industrial General Permits (stormwater)
//   - calepa.ca.gov           CalEPA / CUPA Hazardous Materials Business Plan (hazmat)
//   - www.epa.gov             EPA hazardous-waste generators + national pretreatment
//
// This is intentionally a HOST allowlist, not a URL allowlist: an authoritative
// agency can publish at many paths, but the host is the trust boundary.

export const ALLOWLISTED_HOSTS: ReadonlySet<string> = new Set<string>([
  "www.aqmd.gov",
  "www.waterboards.ca.gov",
  "calepa.ca.gov",
  "www.epa.gov",
  // Additional verified California authorities (registry-expansion programs):
  "leginfo.legislature.ca.gov", // California codes (HSC, Water Code, CCR sections)
  "oehha.ca.gov",               // Proposition 65 list
  "dtsc.ca.gov",                // DTSC hazardous / universal / non-RCRA waste
  "ww2.arb.ca.gov",             // CARB — AB 2588, Title V
  "osfm.fire.ca.gov",           // CAL FIRE OSFM — APSA
  "www.cdph.ca.gov",            // CDPH — medical waste
]);

// Parses the URL and returns true only if its hostname is on the allowlist.
// Returns false for any malformed input (new URL throws) rather than propagating.
export function isAllowlistedUrl(url: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  return ALLOWLISTED_HOSTS.has(parsed.hostname);
}
