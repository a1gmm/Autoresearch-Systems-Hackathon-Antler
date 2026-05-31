import { describe, expect, it } from "vitest";
import { runResearch } from "@/lib/research/run";

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
    expect(hmbp?.verified).toBe(false);
    expect(hmbp?.review_flag).toBe(true);

    const waste = run.determinations.find((determination) =>
      determination.requirement.toLowerCase().includes("waste"),
    );
    expect(waste).toBeDefined();
    expect(waste?.sds_handoff_refs?.map((fact) => fact.field)).toEqual(
      expect.arrayContaining(["hazardous_waste_review"]),
    );
    expect(waste?.verified).toBe(false);
    expect(waste?.review_flag).toBe(true);
  });
});
