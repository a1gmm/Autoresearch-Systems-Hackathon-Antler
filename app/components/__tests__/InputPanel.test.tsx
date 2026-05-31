import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { InputPanel } from "../InputPanel";
import { extractSdsTextFromClientFile } from "@/lib/sds/clientExtraction";

const startRun = vi.hoisted(() => vi.fn());

vi.mock("@/lib/sds/clientExtraction", () => ({
  extractSdsTextFromClientFile: vi.fn()
}));

vi.mock("@/lib/ui/store", () => ({
  useStore: (
    selector: (state: {
      startRun: typeof startRun;
      isRunning: boolean;
      runError: string | null;
      run: null;
    }) => unknown
  ) =>
    selector({
      startRun,
      isRunning: false,
      runError: null,
      run: null
    })
}));

vi.mock("../MissingFactsCard", () => ({
  MissingFactsCard: () => null
}));

vi.mock("../JurisdictionStack", () => ({
  JurisdictionStack: () => null
}));

const mockExtractSdsTextFromClientFile = vi.mocked(extractSdsTextFromClientFile);

describe("InputPanel", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("disables Run while SDS file extraction is pending", async () => {
    let resolveExtraction: (value: Awaited<ReturnType<typeof extractSdsTextFromClientFile>>) => void;
    mockExtractSdsTextFromClientFile.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveExtraction = resolve;
      })
    );
    render(<InputPanel />);

    fireEvent.change(screen.getByPlaceholderText("Describe your project change…"), {
      target: { value: "We use a solvent." }
    });

    const runButton = screen.getByRole("button", { name: /Run/i });
    expect(runButton).toBeEnabled();

    const file = new File(["Section 1"], "pending-sds.txt", {
      type: "text/plain"
    });
    fireEvent.change(screen.getByLabelText("Upload SDS"), {
      target: { files: [file] }
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /Extracting SDS/i })).toBeDisabled();
    });

    fireEvent.click(screen.getByRole("button", { name: /Extracting SDS/i }));
    expect(startRun).not.toHaveBeenCalled();

    resolveExtraction!({
      name: "pending-sds.txt",
      source_type: "pasted_text",
      text: "Section 1",
      text_extraction_status: "ok"
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^Run$/i })).toBeEnabled();
    });
  });

  it("disables scenario starts while SDS extraction is pending and includes SDS after extraction", async () => {
    let resolveExtraction: (value: Awaited<ReturnType<typeof extractSdsTextFromClientFile>>) => void;
    mockExtractSdsTextFromClientFile.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveExtraction = resolve;
      })
    );
    render(<InputPanel />);

    const scenarioButton = screen.getByRole("button", {
      name: /Complex SoCal Manufacturing/i
    });
    expect(scenarioButton).toBeEnabled();

    const file = new File(["Section 1"], "scenario-sds.txt", {
      type: "text/plain"
    });
    fireEvent.change(screen.getByLabelText("Upload SDS"), {
      target: { files: [file] }
    });

    await waitFor(() => {
      expect(scenarioButton).toBeDisabled();
    });

    fireEvent.click(scenarioButton);
    expect(startRun).not.toHaveBeenCalled();

    resolveExtraction!({
      name: "scenario-sds.txt",
      source_type: "pasted_text",
      text: "Section 1",
      text_extraction_status: "ok"
    });

    await waitFor(() => {
      expect(scenarioButton).toBeEnabled();
    });

    fireEvent.click(scenarioButton);

    expect(startRun).toHaveBeenCalledWith(
      expect.objectContaining({
        demo_documents: [
          expect.objectContaining({
            name: "scenario-sds.txt",
            text: "Section 1"
          })
        ]
      })
    );
  });
});
