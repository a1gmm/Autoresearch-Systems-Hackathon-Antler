import { describe, expect, it } from "vitest";
import { toUiResearchRun } from "../pythonRunAdapter";

describe("pythonRunAdapter", () => {
  it("maps Python information requests and scenarios into UI state", () => {
    const run = toUiResearchRun({
      run_id: "run_1",
      status: "needs_information",
      information_requests: [{ field: "chemicals.quantity", question: "How many gallons?", why_needed: "threshold", blocks: ["ca-hmbp"] }],
      scenarios: [{ id: "s1", label: "expected", assumptions: [], rationale: "typical", affects: ["ca-hmbp"] }],
      determinations: [],
      trace_events: [],
      report_markdown: "",
    });
    expect(run.status).toBe("needs_information");
    expect(run.information_requests).toHaveLength(1);
    expect(run.scenarios).toHaveLength(1);
  });

  it("maps nested Task 8 Python result payloads into useful UI rows", () => {
    const run = toUiResearchRun({
      run_id: "run_nested",
      status: "needs_review",
      information_requests: [
        { field: "chemicals.quantity", question: "How many gallons?", why_needed: "HMBP threshold", blocks: ["ca-hmbp"] },
      ],
      scenarios: [
        {
          id: "scenario_expected",
          label: "expected",
          assumptions: [
            { field: "chemicals.quantity", value: 60, unit: "gallons", provenance: "agent_inferred" },
          ],
          rationale: "typical storage tote",
          affects: ["ca-hmbp"],
        },
      ],
      trace_events: [
        {
          type: "event",
          run_id: "run_nested",
          scope: "verify:verdict",
          payload: {
            hypothesis_id: "H-HAZMAT-HMBP",
            raindrop_artifact_id: "rd_artifact_1",
            status: "needs_review",
          },
          created_at: "2026-06-02T12:00:00.000Z",
        },
      ],
      result: {
        run_id: "run_nested",
        determination: {
          status: "needs_review",
          trusted_hypotheses: ["H-AIR-201"],
          needs_review_hypotheses: ["H-HAZMAT-HMBP"],
          reasons: ["HMBP quantity is missing"],
        },
        report: {
          summary: "1 hypotheses passed verification, but 1 require review before relying on the result.",
          coverage: [
            {
              id: "ca-hmbp",
              family: "hazmat",
              status: "blocked_missing_fact",
              reason: "quantity missing",
              project_facts_considered: ["chemicals"],
              missing_facts: ["chemicals.quantity"],
            },
          ],
          evidence_count: 2,
          scenario_count: 1,
        },
        evidence: [
          {
            hypothesis_id: "H-AIR-201",
            sources: [
              {
                url: "https://example.test/rule-201",
                source_name: "Rule 201",
                authority_rank: 1,
                fetched_at: "2026-06-02",
                content_hash: "hash-air",
                effective_date: null,
                quote: "Permit required before construction.",
              },
            ],
            extracted_claims: [],
            researcher_conclusion: "applies",
            uncertainties: [],
          },
          {
            hypothesis_id: "H-HAZMAT-HMBP",
            sources: [],
            extracted_claims: [],
            researcher_conclusion: "needs_review",
            uncertainties: ["quantity missing"],
          },
        ],
        verdicts: [
          {
            hypothesis_id: "H-AIR-201",
            verdict: "pass",
            checks: { grounding: { pass: true, reason: "quote supports claim" } },
            confidence: 0.93,
            repair_tickets: [],
            distrust_reasons: [],
          },
          {
            hypothesis_id: "H-HAZMAT-HMBP",
            verdict: "needs_review",
            checks: { missing_fact: { pass: false, reason: "quantity missing" } },
            confidence: 0.45,
            repair_tickets: [
              {
                ticket_id: "ticket_hmbp",
                hypothesis_id: "H-HAZMAT-HMBP",
                failure_type: "missing_fact",
                failed_check: "missing_fact",
                observed_problem: "quantity missing",
                repair_action: "Ask for chemical quantity",
                max_attempts_remaining: 0,
              },
            ],
            distrust_reasons: ["Cannot verify HMBP threshold without quantity."],
          },
        ],
        information_requests: [
          { field: "chemicals.quantity", question: "How many gallons?", why_needed: "HMBP threshold", blocks: ["ca-hmbp"] },
        ],
        scenarios: [
          {
            id: "scenario_expected",
            label: "expected",
            assumptions: [
              { field: "chemicals.quantity", value: 60, unit: "gallons", provenance: "agent_inferred" },
            ],
            rationale: "typical storage tote",
            affects: ["ca-hmbp"],
          },
        ],
      },
    });

    expect(run.determinations).toEqual([
      expect.objectContaining({
        requirement: "H-AIR-201",
        verified: true,
        review_flag: false,
        confidence: 0.93,
        source_url: "https://example.test/rule-201",
      }),
      expect.objectContaining({
        requirement: "H-HAZMAT-HMBP",
        verified: false,
        review_flag: true,
        confidence: 0.45,
      }),
    ]);
    expect(run.coverage_family_statuses).toEqual([
      expect.objectContaining({ id: "ca-hmbp", family: "hazmat", status: "blocked_missing_fact" }),
    ]);
    expect(run.evidence_bundles).toHaveLength(2);
    expect(run.verification_verdicts).toHaveLength(2);
    expect(run.repair_tickets).toHaveLength(1);
    expect(run.report_markdown).toContain("1 hypotheses passed verification");
    expect(run.trace_events[0]).toEqual(expect.objectContaining({
      artifact_id: "H-HAZMAT-HMBP",
      raindrop_artifact_id: "rd_artifact_1",
      artifact_ids: expect.arrayContaining(["H-HAZMAT-HMBP", "rd_artifact_1"]),
    }));
  });

  it("maps regulatory information-request blocks such as ca-hmbp to coverage families", () => {
    const run = toUiResearchRun({
      run_id: "run_alias",
      status: "needs_information",
      information_requests: [
        { field: "chemicals.quantity", question: "How many gallons?", why_needed: "HMBP threshold", blocks: ["ca-hmbp"] },
      ],
      result: { determination: { status: "needs_information", trusted_hypotheses: [], needs_review_hypotheses: [], reasons: [] } },
    });

    expect(run.coverage_family_statuses).toEqual([
      expect.objectContaining({
        id: "cf-hazmat",
        family: "hazmat",
        status: "blocked_missing_fact",
        missing_facts: ["chemicals.quantity"],
      }),
    ]);
  });

  it("does not create blocked coverage from substring alias collisions", () => {
    const run = toUiResearchRun({
      run_id: "run_bad_alias",
      status: "needs_information",
      information_requests: [
        { field: "repair.notes", question: "What changed?", why_needed: "malformed block", blocks: ["repair", "wildfire"] },
      ],
      result: { determination: { status: "needs_information", trusted_hypotheses: [], needs_review_hypotheses: [], reasons: [] } },
    });

    expect(run.coverage_family_statuses).toEqual([]);
  });

  it("keeps trusted rows in review when the overall Python synthesis needs recall-floor review", () => {
    const run = toUiResearchRun({
      run_id: "run_recall_review",
      status: "needs_review",
      result: {
        determination: {
          status: "needs_review",
          trusted_hypotheses: ["H-AIR-201"],
          needs_review_hypotheses: [],
          reasons: ["Recall floor was not met."],
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
            confidence: 0.91,
            repair_tickets: [],
          },
        ],
      },
    });

    expect(run.determinations).toEqual([
      expect.objectContaining({
        requirement: "H-AIR-201",
        applies: "needs_review",
        verified: false,
        review_flag: true,
      }),
    ]);
  });

  it("normalizes Python Raindrop trace scopes into graph-driving UI phases", () => {
    const run = toUiResearchRun({
      run_id: "run_trace",
      status: "done",
      trace_events: [
        { scope: "plan:complete", payload: { tasks: 2 }, created_at: "2026-06-02T10:00:00.000Z" },
        { scope: "research:bundle", payload: { hypothesis_id: "H-AIR-201" }, created_at: "2026-06-02T10:01:00.000Z" },
        { scope: "verify:verdict", payload: { hypothesis_id: "H-AIR-201", verdict: "pass" }, created_at: "2026-06-02T10:02:00.000Z" },
        { scope: "run:status", payload: { status: "done" }, created_at: "2026-06-02T10:03:00.000Z" },
      ],
      result: { determination: { status: "verified", trusted_hypotheses: [], needs_review_hypotheses: [], reasons: [] } },
    });

    expect(run.trace_events.map((event) => [event.actor, event.phase, event.status])).toEqual([
      ["orchestrator", "coverage", "done"],
      ["orchestrator", "task_graph", "done"],
      ["research_pool", "fanout", "done"],
      ["verifier", "verification", "done"],
      ["synthesis_agent", "matrix", "done"],
    ]);
    expect(run.trace_events[2]).toEqual(expect.objectContaining({
      artifact_id: "H-AIR-201",
    }));
  });

  it("maps Python get_run store records with nested artifacts", () => {
    const run = toUiResearchRun({
      run_id: "run_store",
      status: "done",
      evidence: [
        {
          hypothesis_id: "H-HAZMAT-HMBP",
          sources: [
            {
              url: "https://example.test/hmbp",
              source_name: "CUPA HMBP guidance",
              authority_rank: 1,
              fetched_at: "2026-06-02",
              content_hash: "hash-hmbp",
              effective_date: null,
              quote: "55 gallons triggers reporting.",
            },
          ],
          extracted_claims: [{ field: "chemicals.quantity", value: "60 gallons", source_url: "https://example.test/hmbp", quote: "55 gallons triggers reporting.", confidence: 0.9 }],
          researcher_conclusion: "applies",
          uncertainties: [],
        },
      ],
      verdicts: [
        {
          hypothesis_id: "H-HAZMAT-HMBP",
          verdict: "pass",
          checks: { grounding: { pass: true, reason: "quote supports threshold" } },
          confidence: 0.91,
          repair_tickets: [],
          distrust_reasons: [],
        },
      ],
      result: {
        determination: {
          status: "verified",
          trusted_hypotheses: ["H-HAZMAT-HMBP"],
          needs_review_hypotheses: [],
          reasons: ["All researched hypotheses passed verification."],
        },
        report: { summary: "1 hypotheses passed verification.", evidence_count: 1, scenario_count: 0 },
      },
      artifacts: {
        scope: {
          run_id: "run_store",
          facility: { address: "1 Main St", jurisdiction_stack: ["CUPA"], county: "Los Angeles", city: "Vernon", naics: null, sic: null },
          project_change: { description: "stores solvent", equipment: [], chemicals: [], waste_streams: [], disturbance_acres: null, process_discharge: null },
          missing_facts: [],
          assumptions: [],
        },
        plan: {
          coverage_family_statuses: [
            { id: "cf-hazmat", family: "hazmat", status: "active", reason: "hazardous materials stored", project_facts_considered: ["chemicals"], missing_facts: [] },
          ],
          regulatory_angles: [
            { id: "angle-hmbp", family: "hazmat", label: "HMBP threshold", reason: "quantity threshold", triggering_facts: ["chemicals.quantity"], status: "active" },
          ],
          research_graph: [
            { id: "H-HAZMAT-HMBP", angle_id: "angle-hmbp", family: "hazmat", question: "Does HMBP apply?", required_facts: ["chemicals.quantity"], expected_source_type: "agency_guidance", success_criteria: [], dependencies: [] },
          ],
          research_tasks: [
            { task_id: "T-HMBP", hypothesis_id: "H-HAZMAT-HMBP", assigned_agent: "researcher", allowed_tools: [], blocked_tools: [], budget: { max_sources: 2, max_runtime_seconds: 60, max_model_calls: 1 } },
          ],
        },
        trace_events: [
          {
            type: "event",
            run_id: "run_store",
            scope: "research:bundle",
            payload: { hypothesis_id: "H-HAZMAT-HMBP", raindrop_artifact_id: "rd_bundle" },
            created_at: "2026-06-02T13:00:00.000Z",
          },
        ],
      },
    });

    expect(run.scope_pack.facility.jurisdiction_stack).toEqual(["CUPA"]);
    expect(run.coverage_family_statuses).toEqual([
      expect.objectContaining({ id: "cf-hazmat", family: "hazmat", status: "active" }),
    ]);
    expect(run.regulatory_angles).toHaveLength(1);
    expect(run.research_graph).toEqual([
      expect.objectContaining({ id: "H-HAZMAT-HMBP", family: "hazmat" }),
    ]);
    expect(run.research_tasks).toEqual([
      expect.objectContaining({ task_id: "T-HMBP", hypothesis_id: "H-HAZMAT-HMBP" }),
    ]);
    expect(run.trace_events[0]).toEqual(expect.objectContaining({
      artifact_id: "H-HAZMAT-HMBP",
      raindrop_artifact_id: "rd_bundle",
    }));
    expect(run.determinations[0]).toEqual(expect.objectContaining({
      requirement: "H-HAZMAT-HMBP",
      verified: true,
      review_flag: false,
      source_url: "https://example.test/hmbp",
    }));
  });
});
