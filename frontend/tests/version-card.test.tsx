import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { VersionCard } from "@/components/settings/version-card";

const getAppVersion = vi.fn();
const checkUpdates = vi.fn();
vi.mock("@/lib/api", () => ({
  errText: (e: unknown) => String((e as Error)?.message ?? e),
  getAppVersion: () => getAppVersion(),
  checkUpdates: () => checkUpdates(),
}));

describe("VersionCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getAppVersion.mockResolvedValue({ version: "0.9.0" });
  });
  afterEach(cleanup);

  it("mostra la versione in uso senza che si prema niente", async () => {
    render(<VersionCard />);
    expect(await screen.findByText(/0\.9\.0/)).toBeTruthy();
  });

  it("quando c'è una versione nuova mostra numero, note e link", async () => {
    checkUpdates.mockResolvedValue({
      current: "0.9.0", latest: "0.10.0", update_available: true,
      url: "https://esempio.invalid/v0.10.0", notes: "cose nuove",
    });
    render(<VersionCard />);
    fireEvent.click(await screen.findByRole("button"));
    expect(await screen.findByText(/0\.10\.0/)).toBeTruthy();
    expect(screen.getByText(/cose nuove/)).toBeTruthy();
    const link = screen.getByRole("link") as HTMLAnchorElement;
    expect(link.href).toContain("v0.10.0");
  });

  it("quando si è aggiornati lo dice e non mostra link", async () => {
    checkUpdates.mockResolvedValue({
      current: "0.9.0", latest: "0.9.0", update_available: false,
      url: null, notes: null,
    });
    render(<VersionCard />);
    fireEvent.click(await screen.findByRole("button"));
    await waitFor(() => expect(checkUpdates).toHaveBeenCalled());
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("un controllo fallito NON viene presentato come 'sei aggiornato'", async () => {
    // È l'invariante della funzione: "non lo so" e "sei a posto" sono cose
    // diverse, e confonderle è il modo in cui questa schermata mente.
    checkUpdates.mockRejectedValue(new Error("Impossibile controllare"));
    render(<VersionCard />);
    fireEvent.click(await screen.findByRole("button"));
    expect(await screen.findByText(/impossibile controllare/i)).toBeTruthy();
    expect(screen.queryByText(/aggiornato|up to date/i)).toBeNull();
  });
});
