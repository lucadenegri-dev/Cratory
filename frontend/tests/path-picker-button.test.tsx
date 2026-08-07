import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PathPickerButton } from "@/components/path-picker-button";

const pickPath = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  pickPath: (...args: unknown[]) => pickPath(...args),
}));

afterEach(() => {
  cleanup();
  pickPath.mockReset();
});

describe("PathPickerButton", () => {
  it("il click apre il picker con kind e start e riporta il percorso", async () => {
    pickPath.mockResolvedValue({ path: "/Users/x/Music" });
    const onPick = vi.fn();
    render(<PathPickerButton kind="folder" start="/Users/x" onPick={onPick} onError={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(pickPath).toHaveBeenCalledWith("folder", "/Users/x", undefined);
    expect(onPick).toHaveBeenCalledWith("/Users/x/Music");
  });

  it("annullo (path null) non chiama onPick", async () => {
    pickPath.mockResolvedValue({ path: null });
    const onPick = vi.fn();
    render(<PathPickerButton kind="file" onPick={onPick} onError={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(onPick).not.toHaveBeenCalled();
  });

  it("errore API va a onError", async () => {
    pickPath.mockRejectedValue(new Error("picker occupato"));
    const onError = vi.fn();
    render(<PathPickerButton kind="folder" onPick={() => {}} onError={onError} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect(onError).toHaveBeenCalledWith("picker occupato");
  });

  it("mentre il dialog è aperto il pulsante è disabilitato", async () => {
    // Niente jest-dom nel setup vitest del repo: si legge `disabled` dal nodo.
    let resolvePick!: (v: { path: string | null }) => void;
    pickPath.mockImplementation(() => new Promise((res) => { resolvePick = res; }));
    render(<PathPickerButton kind="folder" onPick={() => {}} onError={() => {}} />);
    await act(async () => {
      fireEvent.click(screen.getByRole("button"));
    });
    expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(true);
    await act(async () => {
      resolvePick({ path: null });
    });
    expect((screen.getByRole("button") as HTMLButtonElement).disabled).toBe(false);
  });
});
