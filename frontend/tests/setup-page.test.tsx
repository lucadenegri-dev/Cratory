import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  usePathname: () => "/setup",
}));

// Il mock deve esporre OGNI export usato dalla pagina: vitest solleva
// "No 'X' export is defined on the mock" al primo accesso mancante
// (stesso pattern di tests/credential-field.test.tsx).
const setSetupCompleted = vi.fn();
vi.mock("@/lib/api", () => ({
  setSetupCompleted: (...a: unknown[]) => setSetupCompleted(...a),
  errText: (e: unknown) => String((e as Error)?.message ?? e),
}));

const { default: SetupPage } = await import("@/app/setup/page");

describe("SetupPage", () => {
  beforeEach(() => { replace.mockClear(); setSetupCompleted.mockReset(); });
  afterEach(cleanup);

  it("scrittura riuscita: porta a /", async () => {
    setSetupCompleted.mockResolvedValue({ completed: true });
    render(<SetupPage />);
    fireEvent.click(screen.getByText("Salta la configurazione"));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });

  it("scrittura fallita: resta sul wizard, mostra l'errore, non naviga", async () => {
    setSetupCompleted.mockRejectedValue(new Error("backend non raggiungibile"));
    render(<SetupPage />);
    fireEvent.click(screen.getByText("Salta la configurazione"));
    await waitFor(() => expect(screen.getByText(/backend non raggiungibile/)).toBeTruthy());
    expect(replace).not.toHaveBeenCalled();
  });
});
