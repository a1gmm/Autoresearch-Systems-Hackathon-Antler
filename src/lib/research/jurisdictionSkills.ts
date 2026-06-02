import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// The county/city jurisdiction skill tree makes the (otherwise unbounded) local
// layer MANAGEABLE by structure: each jurisdiction's local EHS authorities (CUPA,
// fire AHJ, building dept, code amendments) live in their own folder under
// src/lib/research/skills/jurisdictions/<county>/[<city>/]JURISDICTION.md.
//
// The resolver returns whatever folders EXIST for a location and reports the
// rest as explicit gaps — never a guess. Researching a new city = adding its
// folder; the resolver picks it up with no code change.

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "skills", "jurisdictions");

// Strip diacritics so "San José" and "San Jose" both map to the same folder id.
function deaccent(s: string): string {
  return s.normalize("NFD").replace(/[̀-ͯ]/g, "");
}
function slugCounty(county: string): string {
  return deaccent(county).trim().toLowerCase().replace(/\s+/g, "-").replace(/-county$/, "") + "-county";
}
function slugCity(city: string): string {
  return "city-of-" + deaccent(city).trim().toLowerCase().replace(/\s+/g, "-");
}

/** The folder id for a county (and optional city) — the path under jurisdictions/. */
export function jurisdictionSkillId(county: string, city?: string): string {
  const c = slugCounty(county);
  return city ? `${c}/${slugCity(city)}` : c;
}

export type JurisdictionSkill = { id: string; content: string };
export type JurisdictionResolution = {
  county: JurisdictionSkill | null;
  city: JurisdictionSkill | null;
  // Levels expected for this location that have no folder yet (honest gaps).
  gaps: string[];
};

function read(id: string): JurisdictionSkill | null {
  const path = join(ROOT, id, "JURISDICTION.md");
  if (!existsSync(path)) return null;
  return { id, content: readFileSync(path, "utf8") };
}

/** Walk the county/city tree for a location. Returns the skills that exist and
 *  lists the levels that are not yet researched as gaps. */
export function resolveJurisdictionSkills(loc: { county: string; city?: string }): JurisdictionResolution {
  const countyId = slugCounty(loc.county);
  const county = read(countyId);
  const gaps: string[] = [];
  if (!county) gaps.push(`county:${countyId}`);

  let city: JurisdictionSkill | null = null;
  if (loc.city) {
    const cityId = `${countyId}/${slugCity(loc.city)}`;
    city = read(cityId);
    if (!city) gaps.push(`city:${cityId}`);
  }
  return { county, city, gaps };
}
