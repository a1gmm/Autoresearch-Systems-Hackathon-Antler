// Server-side TS read_skill: the just-in-time domain-knowledge reader the
// orchestrator and (future) TS researchers use to orient on a coverage family.
// Mirrors modal/worker_core.py's read_skill_fn. Reference only — never citable
// evidence. ESM-safe path resolution (project is "type":"module").
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SKILLS_DIR = join(dirname(fileURLToPath(import.meta.url)), "skills");

export function availableSkillIds(): string[] {
  if (!existsSync(SKILLS_DIR)) return [];
  return readdirSync(SKILLS_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && existsSync(join(SKILLS_DIR, entry.name, "SKILL.md")))
    .map((entry) => entry.name)
    .sort();
}

export function readSkill(skillId: string): string {
  const path = join(SKILLS_DIR, skillId, "SKILL.md");
  if (!existsSync(path)) {
    throw new Error(`Unknown skill: ${skillId}`);
  }
  return readFileSync(path, "utf8");
}
