import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import DownloadsPage from "@/app/downloads/page";
import type { QueueItem } from "@/lib/api";

afterEach(cleanup);

const item = (over: Partial<QueueItem> = {}): QueueItem => ({
  id: 1, track_id: 10, label: "Aphex Twin — Xtal", kind: "soulseek_auto",
  state: "queued", outcome: null, phase: null, bytes_done: null,
  bytes_total: null, attempts: 0, error: null, position: 0, ...over,
});

const mocks = vi.hoisted(() => ({
  downloadQueue: vi.fn(), cancelQueueItem: vi.fn(),
  moveQueueItemTop: vi.fn(), clearQueueDone: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  downloadQueue: mocks.downloadQueue,
  cancelQueueItem: mocks.cancelQueueItem,
  moveQueueItemTop: mocks.moveQueueItemTop,
  clearQueueDone: mocks.clearQueueDone,
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.downloadQueue.mockResolvedValue({ slots: 3, active: 1, items: [
    item({ id: 1, state: "running", phase: "downloading", bytes_done: 50, bytes_total: 100 }),
    item({ id: 2, state: "queued", label: "B — Due", position: 1 }),
    item({ id: 3, state: "done", outcome: "downloaded", label: "C — Tre", position: 2 }),
  ] });
});

describe("pagina /downloads", () => {
  it("divide la coda in tre fasce e mostra gli slot occupati", async () => {
    render(<DownloadsPage />);
    expect(await screen.findByText("In corso")).toBeTruthy();
    expect(screen.getByText("In attesa")).toBeTruthy();
    expect(screen.getByText("Fatte")).toBeTruthy();
    expect(screen.getByText("1 di 3 in corso")).toBeTruthy();
    expect(screen.getByText("Aphex Twin — Xtal")).toBeTruthy();
    expect(screen.getByText("scarico")).toBeTruthy();
  });

  it("annulla un item e ricarica la coda", async () => {
    mocks.cancelQueueItem.mockResolvedValue({ cancelled: true });
    render(<DownloadsPage />);
    await screen.findByText("B — Due");
    fireEvent.click(screen.getAllByText("Annulla")[0]);
    await waitFor(() => expect(mocks.cancelQueueItem).toHaveBeenCalledWith(1));
    await waitFor(() => expect(mocks.downloadQueue).toHaveBeenCalledTimes(2));
  });

  it("«In cima» c'e' solo sugli item in attesa", async () => {
    render(<DownloadsPage />);
    await screen.findByText("B — Due");
    // un solo item in attesa -> un solo bottone
    expect(screen.getAllByText("In cima")).toHaveLength(1);
    fireEvent.click(screen.getByText("In cima"));
    await waitFor(() => expect(mocks.moveQueueItemTop).toHaveBeenCalledWith(2));
  });

  it("coda vuota: empty state", async () => {
    mocks.downloadQueue.mockResolvedValue({ slots: 3, active: 0, items: [] });
    render(<DownloadsPage />);
    expect(await screen.findByText("Coda vuota")).toBeTruthy();
  });

  it("la barra di avanzamento e' esposta come progressbar con i valori ARIA", async () => {
    render(<DownloadsPage />);
    await screen.findByText("Aphex Twin — Xtal");
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuenow")).toBe("50");
    expect(bar.getAttribute("aria-valuemin")).toBe("0");
    expect(bar.getAttribute("aria-valuemax")).toBe("100");
  });

  it("ricarica la coda anche quando l'azione fallisce", async () => {
    mocks.cancelQueueItem.mockRejectedValue(new Error("Conflitto: gia' concluso"));
    render(<DownloadsPage />);
    await screen.findByText("B — Due");
    fireEvent.click(screen.getAllByText("Annulla")[0]);
    await waitFor(() => expect(mocks.cancelQueueItem).toHaveBeenCalledWith(1));
    // Un giro in piu' oltre al caricamento iniziale: la coda va ricaricata
    // anche se l'azione e' fallita, non solo sul successo.
    await waitFor(() => expect(mocks.downloadQueue).toHaveBeenCalledTimes(2));
    expect(await screen.findByText(/Conflitto: gia' concluso/)).toBeTruthy();
  });

  it("«Svuota lo storico» non fa sparire gli item annullati, mostrati a parte", async () => {
    mocks.downloadQueue.mockResolvedValue({ slots: 3, active: 0, items: [
      item({ id: 3, state: "done", outcome: "downloaded", label: "C — Tre", position: 0 }),
      item({ id: 4, state: "cancelled", label: "D — Quattro", position: 1 }),
    ] });
    mocks.clearQueueDone.mockResolvedValue({ removed: 1 });
    render(<DownloadsPage />);
    await screen.findByText("D — Quattro");
    fireEvent.click(screen.getByText("Svuota lo storico"));
    await waitFor(() => expect(mocks.clearQueueDone).toHaveBeenCalled());
    // L'annullato resta visibile, e vive in una fascia a parte dalla "Fatte"
    // svuotabile: il bottone non deve trovarsi nella stessa sezione.
    expect(await screen.findByText("D — Quattro")).toBeTruthy();
    const cancelledSection = screen.getByText("Annullate").closest("section");
    expect(cancelledSection).not.toBeNull();
    expect(within(cancelledSection as HTMLElement).queryByText("Svuota lo storico")).toBeNull();
  });
});
