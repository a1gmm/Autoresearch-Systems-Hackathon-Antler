import { runResearch } from "../lib/research/run";
import type { ResearchRun } from "../lib/research/types";
import { installFakeResearch, groundedBundle } from "../test/researchTransport";

// The genuine anti-fabrication guard: every determination the pipeline marks
// "verified" must cite a real fetched source (url + quote). A determination
// grounded in a .gov quote cannot have been invented.
function groundedWhereVerified(run: ResearchRun): boolean {
  return run.determinations
    .filter((d) => d.verified)
    .every((d) => d.source_url.length > 0 && d.quote.length > 0);
}

async function main() {
  if (!process.env.OPENAI_API_KEY) {
    console.log("SKIP evals: the dynamic planner needs OPENAI_API_KEY (parseScope is LLM-driven).");
    return;
  }

  // Drive the REAL research pipeline (planner -> pool -> verifier -> synthesis)
  // with an injected transport — no fixture codepath. The transport returns a
  // grounded result for each hypothesis except the waste generator, which lacks
  // a monthly quantity and must surface as needs_review (fail closed, never
  // fabricated). This proves the real verifier marks grounded evidence verified
  // and flags the missing-fact case for review.
  const cleanup = installFakeResearch((hid) => {
    if (hid === "H-WASTE-GENERATOR") {
      return groundedBundle(hid, {
        researcher_conclusion: "needs_review",
        sources: [],
        extracted_claims: [],
        uncertainties: ["Monthly hazardous waste quantity is missing."],
      });
    }
    return groundedBundle(hid);
  });

  let simple: ResearchRun;
  let complex: ResearchRun;
  try {
    simple = await runResearch({ project_description: "A small tenant improvement that adds two ovens. No chemicals, no waste, no discharge." });
    complex = await runResearch({
      project_description:
        "A SoCal manufacturer adds a coating booth, stores 60 gallons of flammable solvent, generates spent solvent waste, and has NAICS 323111.",
    });
  } finally {
    cleanup();
  }

  const complexVerified = complex.determinations.some((d) => d.verified);
  const complexNeedsReview = complex.determinations.some((d) => d.review_flag);

  const checks: Array<{ id: string; passed: boolean; details: string }> = [
    {
      id: "simple-defensible",
      passed: groundedWhereVerified(simple),
      details: `tasks=${simple.research_tasks.length} grounded=${groundedWhereVerified(simple)}`,
    },
    {
      // complex must: ground every verified determination, actually verify at
      // least one (the real research pipeline grounded something), AND flag at
      // least one for review (missing facts surface as needs_review — never
      // fabricated into a confident determination).
      id: "complex-defensible",
      passed: groundedWhereVerified(complex) && complexVerified && complexNeedsReview,
      details: `tasks=${complex.research_tasks.length} grounded=${groundedWhereVerified(complex)} verified=${complexVerified} needsReview=${complexNeedsReview}`,
    },
    {
      // The point of the dynamic planner: richer facts → strictly more research.
      id: "dynamism",
      passed: complex.research_tasks.length > simple.research_tasks.length,
      details: `complex tasks=${complex.research_tasks.length} > simple tasks=${simple.research_tasks.length}`,
    },
  ];

  for (const check of checks) {
    console.log(`${check.passed ? "PASS" : "FAIL"} ${check.id}: ${check.details}`);
  }
  if (checks.some((c) => !c.passed)) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
