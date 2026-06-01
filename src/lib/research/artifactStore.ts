import type { EvidenceBundle } from "./types";

// Artifacts-driven subagent memory. A research subagent does not carry findings
// in ephemeral conversation context; it READS prior artifacts for its hypothesis
// (to resume / accumulate across runs and retries) and WRITES its result as a
// durable artifact. Memory == the artifact store. This interface lets the engine
// stay backend-agnostic: an in-memory store for single-process runs and tests,
// and a durable (Supabase) adapter for long-running detached runs.
export interface ArtifactStore {
  // The grounded result for a hypothesis (latest wins — a better re-research
  // overwrites a weaker prior attempt).
  writeEvidence(run_id: string, bundle: EvidenceBundle): Promise<void>;
  readEvidence(run_id: string, hypothesis_id: string): Promise<EvidenceBundle | null>;
  listEvidence(run_id: string): Promise<EvidenceBundle[]>;

  // Scratch findings a subagent appends as it works, so a resumed/retried run can
  // pick up where it left off instead of re-deriving from scratch.
  appendScratch(run_id: string, hypothesis_id: string, note: string): Promise<void>;
  readScratch(run_id: string, hypothesis_id: string): Promise<string[]>;
}

const key = (run_id: string, hypothesis_id: string) => `${run_id}::${hypothesis_id}`;

// The active artifact store. Defaults to in-memory (single-process runs / tests);
// a durable backend can be installed for detached runs, and tests inject their
// own via __setArtifactStoreForTests. Lazily initialized so the class below is
// defined before first use.
let activeStore: ArtifactStore | null = null;

export function getArtifactStore(): ArtifactStore {
  if (!activeStore) activeStore = new InMemoryArtifactStore();
  return activeStore;
}

export function setArtifactStore(store: ArtifactStore): void {
  activeStore = store;
}

export function __setArtifactStoreForTests(store: ArtifactStore | null): void {
  activeStore = store;
}

// In-memory artifact store: the default for single-process runs, evals, and
// tests. No network, fully deterministic.
export class InMemoryArtifactStore implements ArtifactStore {
  private evidence = new Map<string, EvidenceBundle>();
  private scratch = new Map<string, string[]>();

  async writeEvidence(run_id: string, bundle: EvidenceBundle): Promise<void> {
    this.evidence.set(key(run_id, bundle.hypothesis_id), bundle);
  }

  async readEvidence(run_id: string, hypothesis_id: string): Promise<EvidenceBundle | null> {
    return this.evidence.get(key(run_id, hypothesis_id)) ?? null;
  }

  async listEvidence(run_id: string): Promise<EvidenceBundle[]> {
    const prefix = `${run_id}::`;
    return [...this.evidence.entries()].filter(([k]) => k.startsWith(prefix)).map(([, v]) => v);
  }

  async appendScratch(run_id: string, hypothesis_id: string, note: string): Promise<void> {
    const k = key(run_id, hypothesis_id);
    const notes = this.scratch.get(k) ?? [];
    notes.push(note);
    this.scratch.set(k, notes);
  }

  async readScratch(run_id: string, hypothesis_id: string): Promise<string[]> {
    return [...(this.scratch.get(key(run_id, hypothesis_id)) ?? [])];
  }
}
