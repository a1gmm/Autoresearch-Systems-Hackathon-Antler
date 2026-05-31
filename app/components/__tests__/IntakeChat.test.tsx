import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IntakeChat } from "../IntakeChat";
import { extractSdsTextFromClientFile } from "@/lib/sds/clientExtraction";
import type { IntakeChatResponse } from "@/lib/intake/types";

const startRun = vi.hoisted(() => vi.fn());

vi.mock("@/lib/sds/clientExtraction", () => ({
  extractSdsTextFromClientFile: vi.fn()
}));

vi.mock("@/lib/ui/store", () => ({
  useStore: (selector: (state: { startRun: typeof startRun }) => unknown) =>
    selector({ startRun })
}));

const mockExtractSdsTextFromClientFile = vi.mocked(extractSdsTextFromClientFile);

describe("IntakeChat", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    vi.unstubAllGlobals();
  });

  it("uses latest SDS documents when final intake response completes", async () => {
    const finalResponse = deferred<Response>();
    const onStarted = vi.fn();
    const onSkip = vi.fn();

    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn()
    });
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(
          jsonResponse({
            complete: false,
            message: "Describe the project."
          })
        )
        .mockReturnValueOnce(finalResponse.promise)
    );

    render(<IntakeChat onStarted={onStarted} onSkip={onSkip} />);

    expect(await screen.findByText("Describe the project.")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Type your answer…"), {
      target: { value: "We use a solvent." }
    });
    fireEvent.click(screen.getByLabelText("Send message"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(2);
    });

    fireEvent.change(screen.getByLabelText("SDS text"), {
      target: { value: "Section 1: Identification" }
    });
    fireEvent.click(screen.getByText("Add SDS text"));

    finalResponse.resolve(
      jsonResponse({
        complete: true,
        project_description: "We use a solvent.",
        facts: {}
      })
    );

    await waitFor(() => {
      expect(onStarted).toHaveBeenCalled();
      expect(startRun).toHaveBeenCalledWith({
        project_description: "We use a solvent.",
        demo_documents: [
          expect.objectContaining({
            name: "Pasted SDS",
            type: "sds",
            text: "Section 1: Identification",
            source_type: "pasted_text",
            retention: "ephemeral",
            text_extraction_status: "ok"
          })
        ]
      });
    });
  });

  it("waits for pending SDS extraction before starting a completed intake run", async () => {
    let resolveExtraction: (value: Awaited<ReturnType<typeof extractSdsTextFromClientFile>>) => void;
    const finalResponse = deferred<Response>();
    const onStarted = vi.fn();
    const onSkip = vi.fn();
    mockExtractSdsTextFromClientFile.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveExtraction = resolve;
      })
    );

    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn()
    });
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(
          jsonResponse({
            complete: false,
            message: "Describe the project."
          })
        )
        .mockReturnValueOnce(finalResponse.promise)
    );

    render(<IntakeChat onStarted={onStarted} onSkip={onSkip} />);

    expect(await screen.findByText("Describe the project.")).toBeInTheDocument();

    const file = new File(["Section 1"], "pending-sds.txt", {
      type: "text/plain"
    });
    fireEvent.change(screen.getByLabelText("Upload SDS"), {
      target: { files: [file] }
    });

    await waitFor(() => {
      expect(screen.getByText("Extracting")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Type your answer…"), {
      target: { value: "We use a solvent." }
    });
    fireEvent.click(screen.getByLabelText("Send message"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(2);
    });

    finalResponse.resolve(
      jsonResponse({
        complete: true,
        project_description: "We use a solvent.",
        facts: {}
      })
    );

    await waitFor(() => {
      expect(screen.queryByText(/thinking/)).not.toBeInTheDocument();
    });
    expect(onStarted).not.toHaveBeenCalled();
    expect(startRun).not.toHaveBeenCalled();

    resolveExtraction!({
      name: "pending-sds.txt",
      source_type: "pasted_text",
      text: "Section 1",
      text_extraction_status: "ok"
    });

    await waitFor(() => {
      expect(onStarted).toHaveBeenCalled();
      expect(startRun).toHaveBeenCalledWith({
        project_description: "We use a solvent.",
        demo_documents: [
          expect.objectContaining({
            name: "pending-sds.txt",
            text: "Section 1",
            source_type: "pasted_text"
          })
        ]
      });
    });
  });

  it("starts completed intake with a placeholder when pending SDS extraction rejects", async () => {
    const extraction = deferred<Awaited<ReturnType<typeof extractSdsTextFromClientFile>>>();
    const finalResponse = deferred<Response>();
    const onStarted = vi.fn();
    const onSkip = vi.fn();
    mockExtractSdsTextFromClientFile.mockReturnValueOnce(extraction.promise);

    Object.defineProperty(HTMLElement.prototype, "scrollTo", {
      configurable: true,
      value: vi.fn()
    });
    vi.stubGlobal(
      "fetch",
      vi.fn()
        .mockResolvedValueOnce(
          jsonResponse({
            complete: false,
            message: "Describe the project."
          })
        )
        .mockReturnValueOnce(finalResponse.promise)
    );

    render(<IntakeChat onStarted={onStarted} onSkip={onSkip} />);

    expect(await screen.findByText("Describe the project.")).toBeInTheDocument();

    const file = new File([""], "failed-sds.pdf", {
      type: "application/pdf"
    });
    fireEvent.change(screen.getByLabelText("Upload SDS"), {
      target: { files: [file] }
    });

    await waitFor(() => {
      expect(screen.getByText("Extracting")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Type your answer…"), {
      target: { value: "We use a solvent." }
    });
    fireEvent.click(screen.getByLabelText("Send message"));

    await waitFor(() => {
      expect(fetch).toHaveBeenCalledTimes(2);
    });

    finalResponse.resolve(
      jsonResponse({
        complete: true,
        project_description: "We use a solvent.",
        facts: {}
      })
    );

    await waitFor(() => {
      expect(screen.queryByText(/thinking/)).not.toBeInTheDocument();
    });
    expect(onStarted).not.toHaveBeenCalled();
    expect(startRun).not.toHaveBeenCalled();

    extraction.reject(new Error("PDF extraction failed"));

    await waitFor(() => {
      expect(onStarted).toHaveBeenCalled();
      expect(startRun).toHaveBeenCalledWith({
        project_description: "We use a solvent.",
        demo_documents: [
          expect.objectContaining({
            name: "failed-sds.pdf",
            type: "sds",
            text: "",
            source_type: "pdf",
            retention: "ephemeral",
            text_extraction_status: "needs_pasted_text"
          })
        ]
      });
    });
  });
});

function jsonResponse(body: IntakeChatResponse): Response {
  return {
    ok: true,
    json: async () => body
  } as Response;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve;
    reject = promiseReject;
  });

  return { promise, resolve, reject };
}
