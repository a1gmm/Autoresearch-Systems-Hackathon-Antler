import type { ClientSdsExtraction } from "./types";

export async function extractSdsTextFromClientFile(
  file: File
): Promise<ClientSdsExtraction> {
  if (isPdf(file)) {
    try {
      const pdfjs = await import("pdfjs-dist/legacy/build/pdf.mjs");
      configurePdfWorker(pdfjs);
      const data = new Uint8Array(await file.arrayBuffer());
      const loadingTask = pdfjs.getDocument({ data });
      const pdf = await loadingTask.promise;
      const pages: string[] = [];

      for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
        const page = await pdf.getPage(pageNumber);
        const content = await page.getTextContent();
        pages.push(
          content.items
            .map((item) => ("str" in item ? item.str : ""))
            .join(" ")
        );
      }

      const text = pages.join("\n").trim();
      return {
        name: file.name,
        source_type: "pdf",
        text,
        text_extraction_status: text.length > 0 ? "ok" : "needs_pasted_text"
      };
    } catch {
      return {
        name: file.name,
        source_type: "pdf",
        text: "",
        text_extraction_status: "needs_pasted_text"
      };
    }
  }

  const text = await file.text();
  return {
    name: file.name,
    source_type: "pasted_text",
    text,
    text_extraction_status: text.trim().length > 0 ? "ok" : "empty"
  };
}

function isPdf(file: File): boolean {
  return (
    file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf")
  );
}

function configurePdfWorker(
  pdfjs: typeof import("pdfjs-dist/legacy/build/pdf.mjs")
): void {
  if (pdfjs.GlobalWorkerOptions.workerSrc) {
    return;
  }

  pdfjs.GlobalWorkerOptions.workerSrc = new URL(
    "pdfjs-dist/legacy/build/pdf.worker.mjs",
    import.meta.url
  ).toString();
}
