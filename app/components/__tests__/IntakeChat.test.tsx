import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { IntakeChat } from "../IntakeChat";
import type { IntakeChatResponse } from "@/lib/intake/types";

const startRun = vi.hoisted(() => vi.fn());

vi.mock("@/lib/ui/store", () => ({
  useStore: (selector: (state: { startRun: typeof startRun }) => unknown) =>
    selector({ startRun })
}));

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
