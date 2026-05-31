import { describe, expect, it } from "vitest";
import { extractSdsTextFromClientFile } from "../clientExtraction";

describe("extractSdsTextFromClientFile", () => {
  it("extracts plain text files as pasted text-compatible SDS input", async () => {
    const file = new File(
      ["Section 1: Identification\nSection 2: Hazard(s) identification"],
      "sds.txt",
      { type: "text/plain" }
    );

    const extraction = await extractSdsTextFromClientFile(file);

    expect(extraction).toEqual({
      name: "sds.txt",
      source_type: "pasted_text",
      text: "Section 1: Identification\nSection 2: Hazard(s) identification",
      text_extraction_status: "ok"
    });
  });

  it("marks empty plain text files as empty pasted text input", async () => {
    const file = new File(["   \n"], "empty-sds.txt", { type: "text/plain" });

    const extraction = await extractSdsTextFromClientFile(file);

    expect(extraction).toEqual({
      name: "empty-sds.txt",
      source_type: "pasted_text",
      text: "   \n",
      text_extraction_status: "empty"
    });
  });

  it("returns a pasted text fallback signal when PDF parsing fails", async () => {
    const file = new File(["not a valid pdf"], "scan.pdf", {
      type: "application/pdf"
    });

    const extraction = await extractSdsTextFromClientFile(file);

    expect(extraction.name).toBe("scan.pdf");
    expect(extraction.source_type).toBe("pdf");
    expect(extraction.text_extraction_status).toBe("needs_pasted_text");
  });
});
