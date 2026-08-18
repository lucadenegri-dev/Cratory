import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";

const replace = vi.fn();
let pathname = "/";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => pathname,
}));

const getSetupState = vi.fn();
vi.mock("@/lib/api", () => ({ getSetupState: (...a: unknown[]) => getSetupState(...a) }));

const { SetupGate } = await import("@/components/setup/setup-gate");

describe("SetupGate", () => {
  beforeEach(() => { replace.mockClear(); getSetupState.mockReset(); pathname = "/"; });
  afterEach(cleanup);

  it("porta al wizard al primo avvio", async () => {
    getSetupState.mockResolvedValue({ completed: false });
    render(<SetupGate />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/setup"));
  });

  it("non fa nulla se il wizard è già stato completato", async () => {
    getSetupState.mockResolvedValue({ completed: true });
    render(<SetupGate />);
    await waitFor(() => expect(getSetupState).toHaveBeenCalled());
    expect(replace).not.toHaveBeenCalled();
  });

  it("non reindirizza se si è già sul wizard", async () => {
    pathname = "/setup";
    getSetupState.mockResolvedValue({ completed: false });
    render(<SetupGate />);
    await waitFor(() => expect(getSetupState).toHaveBeenCalled());
    expect(replace).not.toHaveBeenCalled();
  });

  it("col backend giù non manda in un wizard che non può funzionare", async () => {
    getSetupState.mockRejectedValue(new Error("fetch failed"));
    render(<SetupGate />);
    await waitFor(() => expect(getSetupState).toHaveBeenCalled());
    expect(replace).not.toHaveBeenCalled();
  });
});
