import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useStore } from "../store";

describe("store", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
    useStore.getState().reset();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    useStore.getState().reset();
  });

  it("starts in empty state", () => {
    const s = useStore.getState();
    expect(s.run).toBeNull();
    expect(s.replayedEventIds.size).toBe(0);
    expect(s.replayDone).toBe(false);
    expect(s.selectedHypothesisId).toBeNull();
  });

  it("tickReplay adds id and finishReplay flips replayDone", () => {
    const s = useStore.getState();
    s.tickReplay("e1");
    s.tickReplay("e2");
    expect(useStore.getState().replayedEventIds.has("e1")).toBe(true);
    expect(useStore.getState().replayedEventIds.has("e2")).toBe(true);
    s.finishReplay();
    expect(useStore.getState().replayDone).toBe(true);
  });

  it("select sets selected and opens drawer when replayDone", () => {
    const s = useStore.getState();
    s.finishReplay();
    s.select("hyp_x");
    expect(useStore.getState().selectedHypothesisId).toBe("hyp_x");
    expect(useStore.getState().drawerOpen).toBe(true);
  });

  it("select does not open drawer during replay", () => {
    const s = useStore.getState();
    s.select("hyp_x");
    expect(useStore.getState().selectedHypothesisId).toBe("hyp_x");
    expect(useStore.getState().drawerOpen).toBe(false);
  });

  it("polls queued run responses until a terminal run arrives", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse({ run_id: "run_poll", status: "queued" }))
      .mockResolvedValueOnce(jsonResponse({
        run_id: "run_poll",
        status: "done",
        result: {
          determination: {
            status: "verified",
            trusted_hypotheses: ["H-AIR-201"],
            needs_review_hypotheses: [],
            reasons: ["All researched hypotheses passed verification."],
          },
          evidence: [
            {
              hypothesis_id: "H-AIR-201",
              sources: [],
              extracted_claims: [],
              researcher_conclusion: "applies",
              uncertainties: [],
            },
          ],
          verdicts: [
            {
              hypothesis_id: "H-AIR-201",
              verdict: "pass",
              checks: {},
              confidence: 0.92,
              repair_tickets: [],
            },
          ],
        },
      }));
    vi.stubGlobal("fetch", fetchMock);

    await useStore.getState().startRun({ project_description: "queued then done" });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(useStore.getState().run?.status).toBe("queued");
    expect(useStore.getState().isRunning).toBe(true);

    await vi.advanceTimersByTimeAsync(1000);

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock).toHaveBeenLastCalledWith("/api/research/run/run_poll");
    expect(useStore.getState().run?.status).toBe("done");
    expect(useStore.getState().isRunning).toBe(false);

    await vi.advanceTimersByTimeAsync(5000);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

function jsonResponse(body: unknown) {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}
