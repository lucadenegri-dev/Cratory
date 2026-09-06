import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const getDiscoverySettings = vi.fn();
const setDiscoverySettings = vi.fn();
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  getDiscoverySettings: () => getDiscoverySettings(),
  setDiscoverySettings: (s: unknown) => setDiscoverySettings(s),
}));

const { DiscoverySection } = await import("@/components/settings/discovery-section");

afterEach(cleanup);

describe("DiscoverySection", () => {
  it("legge la preferenza e la mostra", async () => {
    getDiscoverySettings.mockResolvedValue({ discogs_enabled: false });
    render(<DiscoverySection />);
    await waitFor(() =>
      expect((screen.getByLabelText(/Offri Discogs/) as HTMLInputElement).checked).toBe(false));
  });

  it("il click salva e riflette la risposta", async () => {
    getDiscoverySettings.mockResolvedValue({ discogs_enabled: true });
    setDiscoverySettings.mockResolvedValue({ discogs_enabled: false });
    render(<DiscoverySection />);
    await waitFor(() => expect(screen.getByLabelText(/Offri Discogs/)).toBeTruthy());
    fireEvent.click(screen.getByLabelText(/Offri Discogs/));
    expect(setDiscoverySettings).toHaveBeenCalledWith({ discogs_enabled: false });
    await waitFor(() =>
      expect((screen.getByLabelText(/Offri Discogs/) as HTMLInputElement).checked).toBe(false));
  });

  it("un salvataggio fallito lo dice e non cambia lo stato", async () => {
    getDiscoverySettings.mockResolvedValue({ discogs_enabled: true });
    setDiscoverySettings.mockRejectedValue(new Error("boom"));
    render(<DiscoverySection />);
    await waitFor(() => expect(screen.getByLabelText(/Offri Discogs/)).toBeTruthy());
    fireEvent.click(screen.getByLabelText(/Offri Discogs/));
    await waitFor(() => expect(screen.getByText(/boom/)).toBeTruthy());
    expect((screen.getByLabelText(/Offri Discogs/) as HTMLInputElement).checked).toBe(true);
  });
});
