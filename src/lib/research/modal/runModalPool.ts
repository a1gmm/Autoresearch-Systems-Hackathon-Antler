import { spawn as nodeSpawn } from "node:child_process";
import type { ChildProcess } from "node:child_process";
import type { EvidenceBundle, ResearchHypothesis, ResearchTask } from "../types";
import { sourceFixtures } from "../fixtures/sources";
import { skillForHypothesis } from "../skillForHypothesis";

const DEFAULT_TIMEOUT_MS = 30_000;
const BUNDLE_MARKER = "PERMITPILOT_BUNDLE_JSON ";
const WORKER_SCRIPT = "src/lib/research/modal/worker.py";

// Indirection so unit tests can inject a fake spawn without depending on
// vitest's module-level vi.mock (which doesn't reach into source-file
// imports of node:* modules in this project's vitest config).
export type SpawnFn = (command: string, args: readonly string[]) => ChildProcess;
const realSpawn: SpawnFn = (cmd, args) =>
  nodeSpawn(cmd, args as string[], { stdio: ["ignore", "pipe", "pipe"] });
let spawnImpl: SpawnFn = realSpawn;
export function __setSpawnForTests(fn: SpawnFn | null): void {
  spawnImpl = fn ?? realSpawn;
}

type SpawnFailure = {
  code: number | null;
  signal: NodeJS.Signals | null;
  stdout: string;
  stderr: string;
};

export async function runModalResearchPool(
  tasks: ResearchTask[],
  hypotheses: ResearchHypothesis[]
): Promise<EvidenceBundle[]> {
  const byId = new Map(hypotheses.map((hypothesis) => [hypothesis.id, hypothesis]));

  const settled = await Promise.allSettled(
    tasks.map(async (task) => {
      const hypothesis = byId.get(task.hypothesis_id);
      if (!hypothesis) {
        throw new Error(`Missing hypothesis for task ${task.task_id}`);
      }
      return runSingleTask(task, hypothesis);
    })
  );

  return settled.map((result, index) => {
    if (result.status === "fulfilled") {
      return result.value;
    }
    return failedBundle(
      tasks[index].hypothesis_id,
      result.reason instanceof Error ? result.reason.message : "Unknown Modal worker failure"
    );
  });
}

async function runSingleTask(
  task: ResearchTask,
  hypothesis: ResearchHypothesis
): Promise<EvidenceBundle> {
  const fixture = sourceFixtures[fixtureForHypothesis(hypothesis.id)];
  const taskSpec = {
    task_id: task.task_id,
    hypothesis_id: hypothesis.id,
    assigned_agent: task.assigned_agent,
    allowed_tools: task.allowed_tools,
    blocked_tools: task.blocked_tools,
    budget: task.budget,
    question: hypothesis.question,
    claim_to_test: hypothesis.claim_to_test ?? null,
    required_facts: hypothesis.required_facts,
    success_criteria: hypothesis.success_criteria,
    skill_id: skillForHypothesis(hypothesis.id),
    source_url: fixture?.url ?? null,
    source_name: fixture?.source_name ?? null,
    authority_rank: fixture?.authority_rank ?? 1,
    effective_date: fixture?.effective_date ?? null,
  };
  const argv = ["run", WORKER_SCRIPT, "--task-json", JSON.stringify(taskSpec)];
  const stdout = await spawnModalRun(argv, DEFAULT_TIMEOUT_MS);
  return parseBundleFromStdout(stdout, hypothesis.id);
}

function fixtureForHypothesis(hypothesisId: string): keyof typeof sourceFixtures | "" {
  const map: Record<string, keyof typeof sourceFixtures> = {
    "H-AIR-201": "scaqmd_rule_201",
    "H-AIR-VOC": "scaqmd_rule_201",
    "H-AIR-219": "scaqmd_rule_219",
    "H-AIR-222": "scaqmd_rule_222",
    "H-STORM-IGP": "industrial_general_permit",
    "H-STORM-CGP": "construction_general_permit",
    "H-HAZMAT-HMBP": "hmbp_threshold_bad",
    "H-WASTE-GENERATOR": "hazardous_waste_generator",
    "H-WASTEWATER-PRETREATMENT": "wastewater_pretreatment",
  };
  return map[hypothesisId] ?? "";
}

function spawnModalRun(argv: string[], timeoutMs: number): Promise<string> {
  return new Promise((resolve, reject) => {
    const child = spawnImpl("modal", argv);
    let stdout = "";
    let stderr = "";
    let timedOut = false;

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGKILL");
    }, timeoutMs);

    child.stdout?.on("data", (chunk: Buffer) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr?.on("data", (chunk: Buffer) => {
      stderr += chunk.toString("utf8");
    });

    child.on("error", (err) => {
      clearTimeout(timer);
      reject(new Error(`Failed to spawn modal CLI: ${err.message}`));
    });

    child.on("close", (code, signal) => {
      clearTimeout(timer);
      if (timedOut) {
        reject(new Error(`modal run timed out after ${timeoutMs}ms. stderr tail: ${tail(stderr)}`));
        return;
      }
      if (code !== 0) {
        const failure: SpawnFailure = { code, signal, stdout, stderr };
        reject(modalFailureError(failure));
        return;
      }
      resolve(stdout);
    });
  });
}

function parseBundleFromStdout(stdout: string, hypothesisId: string): EvidenceBundle {
  const lines = stdout.split(/\r?\n/);
  // Find the marked JSON line (worker.py prints "PERMITPILOT_BUNDLE_JSON {...}").
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i];
    const idx = line.indexOf(BUNDLE_MARKER);
    if (idx === -1) continue;
    const jsonText = line.slice(idx + BUNDLE_MARKER.length).trim();
    try {
      const parsed = JSON.parse(jsonText) as EvidenceBundle;
      if (!parsed.hypothesis_id) {
        parsed.hypothesis_id = hypothesisId;
      }
      return parsed;
    } catch (err) {
      throw new Error(
        `Modal worker output did not parse as JSON for ${hypothesisId}: ${
          err instanceof Error ? err.message : String(err)
        }`
      );
    }
  }
  throw new Error(
    `Modal worker did not emit a ${BUNDLE_MARKER.trim()} line for ${hypothesisId}. stdout tail: ${tail(
      stdout
    )}`
  );
}

function modalFailureError(failure: SpawnFailure): Error {
  const reason = failure.signal
    ? `signal ${failure.signal}`
    : `exit code ${failure.code ?? "unknown"}`;
  return new Error(
    `modal CLI failed with ${reason}. stderr tail: ${tail(failure.stderr)}`
  );
}

function tail(text: string, max = 400): string {
  const trimmed = text.trim();
  if (trimmed.length <= max) return trimmed;
  return `...${trimmed.slice(-max)}`;
}

function failedBundle(hypothesis_id: string, reason: string): EvidenceBundle {
  return {
    hypothesis_id,
    sources: [],
    extracted_claims: [],
    researcher_conclusion: "needs_review",
    uncertainties: [reason],
  };
}
