import { __setFetchForTests } from "@/lib/research/modal/researchPool";
import type { EvidenceBundle } from "@/lib/research/types";

// Test transport: drive the REAL research pool (runModalResearchPool over HTTP)
// by injecting a fake fetch. There is no fixture/deterministic codepath in
// production — tests exercise the real path and supply the bytes the worker
// would have received from Modal. A bundleFor() callback returns the grounded
// EvidenceBundle for each hypothesis_id, so a test controls exactly what the
// "researcher" found without a parallel canned pipeline.

const ENDPOINT = "https://modal.test/run";
const TOKEN = "test-token";

export type BundleFor = (hypothesisId: string, question: string) => EvidenceBundle | { error: string };

/**
 * Point the research pool at a fake Modal endpoint and answer each task with
 * bundleFor(). Returns a cleanup fn (call in afterEach) that clears env + fetch.
 */
export function installFakeResearch(bundleFor: BundleFor): () => void {
  const prevEndpoint = process.env.MODAL_RESEARCH_ENDPOINT;
  const prevToken = process.env.MODAL_RESEARCH_TOKEN;
  process.env.MODAL_RESEARCH_ENDPOINT = ENDPOINT;
  process.env.MODAL_RESEARCH_TOKEN = TOKEN;

  __setFetchForTests(async (_url, init) => {
    const body = JSON.parse(String((init as RequestInit)?.body ?? "{}")) as {
      task_spec?: { hypothesis_id?: string; question?: string };
    };
    const hid = body.task_spec?.hypothesis_id ?? "";
    const question = body.task_spec?.question ?? "";
    const result = bundleFor(hid, question);
    return new Response(JSON.stringify(result), { status: 200, headers: { "content-type": "application/json" } });
  });

  return () => {
    __setFetchForTests(null);
    if (prevEndpoint === undefined) delete process.env.MODAL_RESEARCH_ENDPOINT;
    else process.env.MODAL_RESEARCH_ENDPOINT = prevEndpoint;
    if (prevToken === undefined) delete process.env.MODAL_RESEARCH_TOKEN;
    else process.env.MODAL_RESEARCH_TOKEN = prevToken;
  };
}

/**
 * A grounded EvidenceBundle helper — a real-shaped "applies" result with a
 * source quote. Tests use this to stand in for a successful researcher run.
 */
export function groundedBundle(hypothesisId: string, opts?: Partial<EvidenceBundle>): EvidenceBundle {
  return {
    hypothesis_id: hypothesisId,
    sources: [
      {
        url: "https://www.govinfo.gov/test-source",
        source_name: "Test primary source",
        authority_rank: 1,
        fetched_at: "2026-06-01T00:00:00Z",
        content_hash: "sha256:test",
        effective_date: "2025-01-01",
        quote: "The threshold for this requirement is met.",
      },
    ],
    extracted_claims: [
      {
        field: "threshold",
        value: "met",
        source_url: "https://www.govinfo.gov/test-source",
        quote: "The threshold for this requirement is met.",
        confidence: 0.9,
      },
    ],
    researcher_conclusion: "applies",
    uncertainties: [],
    ...opts,
  };
}
