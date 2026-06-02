import { create } from "zustand";
import type { ResearchRun, ResearchRunInput, CoverageFamily } from "@/lib/research/types";
import { toUiResearchRun } from "@/lib/research/pythonRunAdapter";

export type ReplaySpeed = 1 | 2;

export type MatrixFilter = "all" | "verified" | "needs_review" | "failed" | "blocked";

export type Store = {
  run: ResearchRun | null;
  isRunning: boolean;
  runError: string | null;
  replayedEventIds: Set<string>;
  replayDone: boolean;
  selectedHypothesisId: string | null;
  drawerOpen: boolean;
  replaySpeed: ReplaySpeed;
  matrixFilter: MatrixFilter;
  reportFamily: CoverageFamily | null;
  openReport: (family: CoverageFamily) => void;
  closeReport: () => void;
  startRun: (payload: ResearchRunInput) => Promise<void>;
  tickReplay: (eventId: string) => void;
  finishReplay: () => void;
  select: (id: string | null) => void;
  setDrawerOpen: (open: boolean) => void;
  setSpeed: (s: ReplaySpeed) => void;
  setMatrixFilter: (f: MatrixFilter) => void;
  reset: () => void;
};

const initial = {
  run: null,
  isRunning: false,
  runError: null,
  replayDone: false,
  selectedHypothesisId: null,
  drawerOpen: false,
  replaySpeed: 1 as ReplaySpeed,
  matrixFilter: "all" as MatrixFilter,
  reportFamily: null as CoverageFamily | null,
};

const POLL_MS = 1000;
let activeStartToken = 0;
let activePollTimer: ReturnType<typeof setTimeout> | null = null;

function clearActivePoll() {
  if (activePollTimer) clearTimeout(activePollTimer);
  activePollTimer = null;
}

function isTerminalRunStatus(status: ResearchRun["status"]) {
  return status === "done" || status === "needs_review" || status === "needs_information" || status === "failed";
}

export const useStore = create<Store>((set, get) => {
  function schedulePoll(runId: string, token: number) {
    clearActivePoll();
    activePollTimer = setTimeout(() => {
      void pollRun(runId, token);
    }, POLL_MS);
  }

  async function pollRun(runId: string, token: number): Promise<void> {
    try {
      const res = await fetch(`/api/research/run/${runId}`);
      if (!res.ok) throw new Error(`Run poll failed: HTTP ${res.status}`);
      const run = toUiResearchRun(await res.json());
      if (token !== activeStartToken) return;

      const terminal = isTerminalRunStatus(run.status);
      set({ run, isRunning: !terminal });
      if (terminal) {
        clearActivePoll();
      } else {
        schedulePoll(run.run_id, token);
      }
    } catch (e) {
      if (token !== activeStartToken) return;
      clearActivePoll();
      set({ isRunning: false, runError: e instanceof Error ? e.message : String(e) });
    }
  }

  return {
    ...initial,
    replayedEventIds: new Set<string>(),
    startRun: async (payload) => {
      const token = ++activeStartToken;
      clearActivePoll();
      set({ ...initial, replayedEventIds: new Set(), isRunning: true });
      try {
        const res = await fetch("/api/research/run", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!res.ok) throw new Error(`Run failed: HTTP ${res.status}`);
        const run = toUiResearchRun(await res.json());
        if (token !== activeStartToken) return;

        const terminal = isTerminalRunStatus(run.status);
        set({ run, isRunning: !terminal });
        if (!terminal) schedulePoll(run.run_id, token);
      } catch (e) {
        if (token !== activeStartToken) return;
        clearActivePoll();
        set({ isRunning: false, runError: e instanceof Error ? e.message : String(e) });
      }
    },
    tickReplay: (eventId) => {
      const next = new Set(get().replayedEventIds);
      next.add(eventId);
      set({ replayedEventIds: next });
    },
    finishReplay: () => set({ replayDone: true }),
    select: (id) => set({ selectedHypothesisId: id, drawerOpen: id !== null && get().replayDone }),
    setDrawerOpen: (drawerOpen) => set({ drawerOpen }),
    setSpeed: (replaySpeed) => set({ replaySpeed }),
    setMatrixFilter: (matrixFilter) => set({ matrixFilter }),
    openReport: (family) => set({ reportFamily: family }),
    closeReport: () => set({ reportFamily: null }),
    reset: () => {
      activeStartToken += 1;
      clearActivePoll();
      set({ ...initial, replayedEventIds: new Set() });
    },
  };
});
