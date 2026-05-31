import { describe, expect, it } from "vitest";
import type { SdsReview } from "@/lib/sds/types";
import type { ScopePack } from "@/lib/research/types";
import { runResearch } from "@/lib/research/run";
import { applySdsHandoffToScope } from "@/lib/research/scope";
import { synthesize } from "@/lib/research/synthesis";

const SDS_TEXT = `
Section 1: Identification
Product identifier: Solvent Blend 42.
Manufacturer: Antler Coatings LLC.
Emergency phone: CHEMTREC 1-800-424-9300.
Revision date: January 3, 2025.

Section 2: Hazard(s) identification
Danger. Highly flammable liquid and vapor. Causes serious eye irritation.
Pictograms: flame, exclamation mark.

Section 3: Composition/information on ingredients
Acetone CAS 67-64-1 40-60%.
Toluene CAS 108-88-3 10-20%.

Section 4: First-aid measures
Move exposed person to fresh air.

Section 5: Fire-fighting measures
Use dry chemical, alcohol-resistant foam, or carbon dioxide.

Section 6: Accidental release measures
Contain spill with inert absorbent. Prevent entry into waterways and storm drains.

Section 7: Handling and storage
Store in a flammable liquid storage cabinet. Keep away from ignition sources.

Section 8: Exposure controls/personal protection
Use chemical splash goggles, nitrile gloves, and local exhaust ventilation.

Section 9: Physical and chemical properties
Flash point: -4 F. VOC content: 620 g/L. Vapor pressure: 180 mmHg at 20 C.

Section 10: Stability and reactivity
Incompatible materials include strong oxidizers and strong acids.

Section 11: Toxicological information
Inhalation may cause drowsiness or dizziness.

Section 12: Ecological information
Toxic to aquatic life. Avoid release to the environment.

Section 13: Disposal considerations
Dispose of contents and containers as hazardous waste in accordance with federal, state, and local regulations.

Section 14: Transport information
UN1993, Flammable liquids, n.o.s., Class 3, Packing Group II.

Section 15: Regulatory information
California Proposition 65: This product contains toluene known to the State of California to cause birth defects.

Section 16: Other information
Prepared by EHS. Revision date: January 3, 2025.
`;

describe("research run SDS integration", () => {
  it("ignores SDS handoff facts that are not active review-flagged facts", () => {
    const scope: ScopePack = {
      run_id: "run_sds_regression",
      facility: {
        address: "Southern California light industrial site",
        jurisdiction_stack: ["California Water Boards"],
        naics: null,
        sic: null,
      },
      project_change: {
        description: "Construction project with no confirmed chemical inventory.",
        equipment: [],
        chemicals: [],
        waste_streams: [],
        disturbance_acres: 1.2,
        process_discharge: false,
      },
      missing_facts: [],
      assumptions: [],
    };
    const review = {
      document: {
        id: "run_sds_regression_sds_1",
        run_id: "run_sds_regression",
        name: "Unreviewed SDS",
        source_type: "pasted_text",
        retention: "ephemeral",
        extracted_text: SDS_TEXT,
        text_extraction_status: "ok",
      },
      section_map: {
        document_id: "run_sds_regression_sds_1",
        sections: [],
      },
      overall_status: "complete",
      quality_findings: [],
      safety_findings: [],
      permit_handoff_facts: [
        {
          field: "hazardous_material_inventory_review",
          value: true,
          source_section: 2,
          quote: "Danger. Highly flammable liquid and vapor.",
          confidence: 0.85,
          review_flag: false,
          reason: "Synthetic non-review-flagged fact must not alter scope.",
        },
        {
          field: "hazardous_waste_review",
          value: true,
          source_section: 13,
          quote: "Dispose as hazardous waste.",
          confidence: 0.85,
          review_flag: false,
          reason: "Synthetic non-review-flagged fact must not alter scope.",
        },
        {
          field: "hazardous_material_inventory_review",
          value: false,
          source_section: 2,
          quote: "No hazardous material inventory review indicated.",
          confidence: 0.85,
          review_flag: true,
          reason: "Synthetic false-valued fact must not alter scope.",
        },
      ],
    } satisfies SdsReview;

    const augmentedScope = applySdsHandoffToScope(scope, [review]);

    expect(augmentedScope).toBe(scope);
    expect(augmentedScope.project_change.chemicals).toEqual([]);
    expect(augmentedScope.project_change.waste_streams).toEqual([]);
    expect(augmentedScope.missing_facts).toEqual([]);
    expect(augmentedScope.assumptions).toEqual([]);
  });

  it("omits false or null review-flagged SDS facts from determination refs", () => {
    const scope: ScopePack = {
      run_id: "run_sds_synthesis_regression",
      facility: {
        address: "Los Angeles County manufacturing facility",
        jurisdiction_stack: ["SCAQMD"],
        naics: "332813",
        sic: "3471",
      },
      project_change: {
        description: "Coating booth with solvent use.",
        equipment: [{ kind: "coating_booth", description: "new emitting equipment" }],
        chemicals: [{ name: "flammable solvent", quantity: 60, unit: "gallons", hazard: "flammable" }],
        waste_streams: [],
        disturbance_acres: 0,
        process_discharge: false,
      },
      missing_facts: [],
      assumptions: [],
    };
    const review = {
      document: {
        id: "run_sds_synthesis_regression_sds_1",
        run_id: "run_sds_synthesis_regression",
        name: "VOC SDS",
        source_type: "pasted_text",
        retention: "ephemeral",
        extracted_text: SDS_TEXT,
        text_extraction_status: "ok",
      },
      section_map: {
        document_id: "run_sds_synthesis_regression_sds_1",
        sections: [],
      },
      overall_status: "complete",
      quality_findings: [],
      safety_findings: [],
      permit_handoff_facts: [
        {
          field: "voc_air_emissions_review",
          value: true,
          source_section: 9,
          quote: "VOC content: 620 g/L.",
          confidence: 0.85,
          review_flag: true,
          reason: "True candidate fact should be emitted as metadata.",
        },
        {
          field: "voc_air_emissions_review",
          value: false,
          source_section: 9,
          quote: "No VOC review indicated.",
          confidence: 0.85,
          review_flag: true,
          reason: "False candidate fact should not be emitted.",
        },
        {
          field: "voc_air_emissions_review",
          value: null,
          source_section: 9,
          quote: "VOC review unknown.",
          confidence: 0.4,
          review_flag: true,
          reason: "Null candidate fact should not be emitted.",
        },
      ],
    } satisfies SdsReview;

    const result = synthesize(
      scope,
      [
        {
          id: "H-AIR-VOC",
          angle_id: "A-AIR-EMITTING-EQUIPMENT",
          family: "air",
          question: "Do solvent VOC emissions require additional review?",
          required_facts: [],
          expected_source_type: "regulation",
          success_criteria: [],
          dependencies: [],
        },
      ],
      [
        {
          id: "A-AIR-EMITTING-EQUIPMENT",
          family: "air",
          label: "New or modified emitting equipment",
          reason: "Coating or process equipment may require air district authorization.",
          triggering_facts: [],
          status: "active",
        },
      ],
      [],
      [],
      [review],
    );

    expect(result.determinations[0].sds_handoff_refs).toEqual([
      expect.objectContaining({
        field: "voc_air_emissions_review",
        value: true,
        document_id: "run_sds_synthesis_regression_sds_1",
        document_name: "VOC SDS",
      }),
    ]);
  });

  it("reviews SDS documents and carries handoff refs without bypassing verification", async () => {
    const run = await runResearch({
      project_description:
        "A Southern California light industrial construction project disturbing 1.2 acres with no chemical inventory provided.",
      demo_documents: [
        {
          name: "Solvent Blend 42 SDS",
          type: "sds",
          source_type: "pasted_text",
          retention: "ephemeral",
          text_extraction_status: "ok",
          text: SDS_TEXT,
        },
      ],
    });

    expect(run.sds_reviews).toHaveLength(1);
    expect(run.sds_reviews[0].permit_handoff_facts.length).toBeGreaterThan(0);
    expect(run.sds_reviews[0].permit_handoff_facts.every((fact) => fact.review_flag)).toBe(true);
    expect(run.trace_events).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          actor: "sds_reviewer",
          phase: "sds_review",
          status: "done",
          artifact_id: run.sds_reviews[0].document.id,
        }),
      ]),
    );

    const allHandoffRefs = run.determinations.flatMap((determination) => determination.sds_handoff_refs ?? []);
    expect(allHandoffRefs.length).toBeGreaterThan(0);
    expect(allHandoffRefs.every((fact) => fact.document_id.length > 0 && fact.document_name.length > 0)).toBe(true);
    expect(run.determinations.every((determination) => !determination.source_url.startsWith("sds:"))).toBe(true);
    expect(
      run.determinations.every((determination) =>
        determination.verified
          ? determination.source_url.length > 0 && !determination.source_url.startsWith("sds:")
          : determination.review_flag,
      ),
    ).toBe(true);

    const hmbp = run.determinations.find((determination) =>
      determination.requirement.toLowerCase().includes("hmbp"),
    );
    expect(hmbp).toBeDefined();
    expect(hmbp?.sds_handoff_refs?.map((fact) => fact.field)).toEqual(
      expect.arrayContaining(["hazardous_material_inventory_review"]),
    );
    expect(hmbp?.sds_handoff_refs?.map((fact) => fact.field) ?? []).not.toContain("california_ehs_review");
    expect(hmbp?.verified).toBe(false);
    expect(hmbp?.review_flag).toBe(true);

    const waste = run.determinations.find((determination) =>
      determination.requirement.toLowerCase().includes("waste"),
    );
    expect(waste).toBeDefined();
    expect(waste?.sds_handoff_refs?.map((fact) => fact.field)).toEqual(
      expect.arrayContaining(["hazardous_waste_review"]),
    );
    expect(waste?.sds_handoff_refs?.map((fact) => fact.field) ?? []).not.toContain("california_ehs_review");
    expect(waste?.verified).toBe(false);
    expect(waste?.review_flag).toBe(true);

    const constructionStormwater = run.determinations.find((determination) =>
      determination.requirement.toLowerCase().includes("construction stormwater"),
    );
    expect(constructionStormwater).toBeDefined();
    expect(constructionStormwater?.sds_handoff_refs?.map((fact) => fact.field) ?? []).not.toContain(
      "spill_stormwater_containment_review",
    );
  });

  it("attaches VOC SDS refs with provenance only to VOC determinations", async () => {
    const run = await runResearch({
      project_description:
        "A Los Angeles County manufacturer is adding a coating booth and storing 60 gallons of a new flammable solvent.",
      demo_documents: [
        {
          name: "Solvent Blend 42 SDS",
          type: "sds",
          source_type: "pasted_text",
          retention: "ephemeral",
          text_extraction_status: "ok",
          text: SDS_TEXT,
        },
        {
          name: "Backup Solvent Blend 42 SDS",
          type: "sds",
          source_type: "pasted_text",
          retention: "ephemeral",
          text_extraction_status: "ok",
          text: SDS_TEXT,
        },
      ],
    });

    const permit201 = run.determinations.find((determination) =>
      determination.requirement.toLowerCase().includes("permit to construct"),
    );
    const voc = run.determinations.find((determination) =>
      determination.requirement.toLowerCase().includes("voc"),
    );
    const rule219 = run.determinations.find((determination) =>
      determination.requirement.toLowerCase().includes("rule 219"),
    );
    const rule222 = run.determinations.find((determination) =>
      determination.requirement.toLowerCase().includes("rule 222"),
    );
    const vocRefs = voc?.sds_handoff_refs?.filter((fact) => fact.field === "voc_air_emissions_review") ?? [];

    expect(vocRefs).toHaveLength(2);
    expect(vocRefs.map((fact) => ({ id: fact.document_id, name: fact.document_name }))).toEqual(
      run.sds_reviews.map((review) => ({ id: review.document.id, name: review.document.name })),
    );
    expect(permit201?.sds_handoff_refs?.map((fact) => fact.field) ?? []).not.toContain("voc_air_emissions_review");
    expect(rule219?.sds_handoff_refs?.map((fact) => fact.field) ?? []).not.toContain("voc_air_emissions_review");
    expect(rule222?.sds_handoff_refs?.map((fact) => fact.field) ?? []).not.toContain("voc_air_emissions_review");
    expect(run.determinations.every((determination) => !determination.source_url.startsWith("sds:"))).toBe(true);
  });
});
