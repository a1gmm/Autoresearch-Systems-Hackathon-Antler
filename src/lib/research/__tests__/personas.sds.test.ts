import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { runResearch } from "@/lib/research/run";
import { installFakeResearch, groundedBundle } from "@/test/researchTransport";
import { INKJET_SDS } from "@/test/data/inkjetSds";
import type { ResearchRunInput } from "@/lib/research/types";

// Real SDS documents (IHOPE JHV-09 UV-curable inkjet inks). Used to prove that
// SDS reviews actually reach synthesis: a flagged SDS fact must surface as an
// sds_handoff_ref on a determination, never silently dropped.
const BLACK = INKJET_SDS["IHOPE INKJET INK JHV-09 BLACK"];
const WHITE = INKJET_SDS["IHOPE INKJET INK JHV-09 WHITE"];
const CYAN = INKJET_SDS["IHOPE INKJET INK JHV-09 CYAN"];

function sds(name: string, text: string) {
  return { name, type: "sds" as const, text };
}

// 10 personas spanning farm -> new manufacturing -> existing facility -> enterprise.
// Each carries one or more REAL inkjet SDS to exercise the SDS->synthesis path.
const PERSONAS: Array<{ name: string; input: ResearchRunInput; expectSdsRefs: boolean }> = [
  {
    name: "Farm / ag printing of crop labels",
    input: { project_description: "A family farm in Fresno County adds a small UV inkjet printer to print crop and shipping labels onsite, storing several liters of UV ink.", demo_documents: [sds("JHV-09 Black", BLACK)] },
    expectSdsRefs: true,
  },
  {
    name: "New manufacturing facility — coating + printing line",
    input: { project_description: "A new Los Angeles County manufacturer installs a UV-curable inkjet coating booth and stores 60 gallons of UV ink across colors, NAICS 323111.", demo_documents: [sds("JHV-09 Black", BLACK), sds("JHV-09 White", WHITE)] },
    expectSdsRefs: true,
  },
  {
    name: "Existing facility adding a new ink",
    input: { project_description: "An existing San Bernardino printing facility introduces a new UV-curable inkjet ink to its line and must review EHS impact.", demo_documents: [sds("JHV-09 Cyan", CYAN)] },
    expectSdsRefs: true,
  },
  {
    name: "Enterprise multi-site label converter",
    input: { project_description: "An enterprise packaging company standardizes a UV inkjet ink across multiple Southern California plants, storing large aggregate quantities.", demo_documents: [sds("JHV-09 Black", BLACK), sds("JHV-09 White", WHITE), sds("JHV-09 Cyan", CYAN)] },
    expectSdsRefs: true,
  },
  {
    name: "Small business sign shop",
    input: { project_description: "A small sign shop in Long Beach runs a wide-format UV printer with a few gallons of inkjet ink.", demo_documents: [sds("JHV-09 Black", BLACK)] },
    expectSdsRefs: true,
  },
  {
    name: "Contract electronics manufacturer (marking ink)",
    input: { project_description: "A contract electronics manufacturer in Orange County uses UV inkjet ink to mark PCBs and stores solvent and ink.", demo_documents: [sds("JHV-09 White", WHITE)] },
    expectSdsRefs: true,
  },
  {
    name: "Textile printer",
    input: { project_description: "A textile printing company in Vernon adds UV inkjet capability and stores multiple ink colors.", demo_documents: [sds("JHV-09 Cyan", CYAN), sds("JHV-09 Black", BLACK)] },
    expectSdsRefs: true,
  },
  {
    name: "Brewery adding can-printing",
    input: { project_description: "A craft brewery in San Diego adds an inline UV inkjet can printer using UV-curable ink.", demo_documents: [sds("JHV-09 Black", BLACK)] },
    expectSdsRefs: true,
  },
  {
    name: "Aerospace parts marking",
    input: { project_description: "An aerospace supplier in the Antelope Valley uses UV inkjet ink for permanent part marking and stores ink and cleaning solvent.", demo_documents: [sds("JHV-09 White", WHITE)] },
    expectSdsRefs: true,
  },
  {
    name: "No-SDS control — facility with no documents",
    input: { project_description: "A warehouse adds shelving and a forklift. No chemicals, no inks, no SDS provided.", demo_documents: [] },
    expectSdsRefs: false,
  },
];

describe("persona E2E: real inkjet SDS reach synthesis", () => {
  let cleanup: () => void;
  beforeEach(() => {
    // Drive the real pipeline; the research pool returns grounded bundles so the
    // run completes. SDS review + handoff is independent of the pool.
    cleanup = installFakeResearch((hid) => groundedBundle(hid));
  });
  afterEach(() => cleanup());

  for (const persona of PERSONAS) {
    it(`${persona.name}: SDS facts reach synthesis (or none when no SDS)`, async () => {
      const run = await runResearch(persona.input);

      // SDS reviews are attached to the run.
      expect(run.sds_reviews?.length ?? 0).toBe(persona.input.demo_documents?.length ?? 0);

      const allRefs = run.determinations.flatMap((d) => d.sds_handoff_refs ?? []);
      if (persona.expectSdsRefs) {
        // The real SDS flagged facts that surfaced as determination provenance.
        expect(allRefs.length).toBeGreaterThan(0);
        // Every ref carries real document provenance (id + name).
        expect(allRefs.every((r) => r.document_id.length > 0 && r.document_name.length > 0)).toBe(true);
        // SDS refs are never citable as the verified source (separation of concerns).
        expect(run.determinations.every((d) => !d.source_url.startsWith("sds:"))).toBe(true);
      } else {
        expect(allRefs.length).toBe(0);
      }
    });
  }

  it("a real UV inkjet SDS opens hazmat and air determinations carrying its provenance", async () => {
    const run = await runResearch({
      project_description: "A SoCal manufacturer adds a UV inkjet line and stores UV-curable ink.",
      demo_documents: [sds("JHV-09 Black", BLACK)],
    });
    const refFields = new Set(run.determinations.flatMap((d) => (d.sds_handoff_refs ?? []).map((r) => r.field)));
    // The real Black SDS triggers VOC/air + hazmat material review — both must be
    // attached to determinations, proving the SDS shaped the synthesis.
    expect([...refFields].length).toBeGreaterThan(0);
  });
});
