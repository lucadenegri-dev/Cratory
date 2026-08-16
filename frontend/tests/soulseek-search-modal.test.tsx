import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { SoulseekSearchModal } from "@/components/soulseek-search-modal";
import type { DownloadStatus, SoulseekSearchFile } from "@/lib/api";

afterEach(cleanup);

const file = (over: Partial<SoulseekSearchFile> = {}): SoulseekSearchFile => ({
  username: "user1", filename: "Music\\Aphex Twin\\Xtal.flac", size: 30_000_000,
  bitrate: null, length: 294, format: null, has_free_slot: true, queue_length: 0,
  upload_speed: null, score: 120, confidence: 0.9, auto_ok: true, ...over,
});

const mocks = vi.hoisted(() => ({
  soulseekSearch: vi.fn(),
  downloadReview: vi.fn(),
  enqueueDownloads: vi.fn(),
  slskdStatus: vi.fn(),
}));

// Si sostituiscono solo le funzioni usate dal modal; il resto del modulo resta vero
// (fmtDuration/fmtSize e i tipi servono davvero).
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  soulseekSearch: mocks.soulseekSearch,
  downloadReview: mocks.downloadReview,
  enqueueDownloads: mocks.enqueueDownloads,
  slskdStatus: mocks.slskdStatus,
}));

const target = { track_id: 1, artist: "Aphex Twin", title: "Xtal" };

// La coda parallela (B) fa restare /api/downloads/status a "running" per
// tutta la vita della coda, non piu' per un singolo download: il vecchio
// gate `available && !running` del modal spegneva "Scarica questo" appena
// una qualsiasi traccia era in coda. Stesso gate gia' rimosso dalla pagina
// wishlist (vedi tests/wishlist-download-gate.test.tsx) e per lo stesso
// motivo.
const downloadStatus = (over: Partial<DownloadStatus> = {}): DownloadStatus => ({
  available: true, status: "idle", processed: 0, total: 0, downloaded: 0,
  needs_review: 0, not_found: 0, failed: 0, playlist_id: null, items: [],
  error: null, current_label: null, ...over,
});

const jobsMock = vi.hoisted(() => ({ useJobs: vi.fn() }));
vi.mock("@/components/jobs-provider", () => ({ useJobs: jobsMock.useJobs }));

beforeEach(() => {
  vi.clearAllMocks();
  jobsMock.useJobs.mockReturnValue({ download: downloadStatus(), refresh: vi.fn() });
  mocks.downloadReview.mockResolvedValue({
    expected: { artist: "Aphex Twin", title: "Xtal", duration_seconds: 294 },
    downloaded: null, reason: null,
  });
  mocks.slskdStatus.mockResolvedValue({ web_url: "http://localhost:5030" });
  mocks.soulseekSearch.mockResolvedValue({
    variants: ["Aphex Twin Xtal", "Aphex Twin"],
    results: [file(), file({ username: "user2", filename: "b1 rip.mp3", bitrate: 128,
                             score: 40, confidence: 0.3, auto_ok: false })],
  });
});

describe("SoulseekSearchModal", () => {
  it("all'apertura lancia la ricerca con la query precompilata", async () => {
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    await waitFor(() => expect(mocks.soulseekSearch).toHaveBeenCalledWith("Aphex Twin Xtal", 1));
    expect(await screen.findByText("Xtal.flac")).toBeTruthy();
    expect(screen.getByText("b1 rip.mp3")).toBeTruthy();  // nessun filtro a soglia
    expect(screen.getByText("affidabile")).toBeTruthy();  // badge solo sul candidato auto_ok
  });

  it("le varianti compilano il campo e rilanciano la ricerca", async () => {
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    await screen.findByText("Xtal.flac");
    fireEvent.click(screen.getByRole("button", { name: "Aphex Twin" }));
    await waitFor(() => expect(mocks.soulseekSearch).toHaveBeenLastCalledWith("Aphex Twin", 1));
    expect((screen.getByLabelText("Query di ricerca Soulseek") as HTMLInputElement).value)
      .toBe("Aphex Twin");
  });

  it("«Scarica questo» accoda il candidato scelto", async () => {
    mocks.enqueueDownloads.mockResolvedValue({ enqueued: 1, skipped: 0 });
    const onPicked = vi.fn();
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={onPicked} />);
    await screen.findByText("Xtal.flac");
    fireEvent.click(screen.getAllByText("Scarica questo")[0]);
    await waitFor(() => expect(mocks.enqueueDownloads).toHaveBeenCalledWith([1],
      expect.objectContaining({
        candidate: expect.objectContaining({ username: "user1" }),
      })));
    await waitFor(() => expect(onPicked).toHaveBeenCalled());
  });

  it("la coda in lavorazione (status=running) non spegne «Scarica questo»", async () => {
    // Stesso motivo del gate della wishlist: /api/downloads/status resta
    // "running" per tutta la vita della coda parallela, non piu' per un
    // singolo download in corso.
    jobsMock.useJobs.mockReturnValue({ download: downloadStatus({ status: "running" }), refresh: vi.fn() });
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    await screen.findByText("Xtal.flac");
    const btn = screen.getAllByText("Scarica questo")[0].closest("button") as HTMLButtonElement;
    expect(btn.disabled).toBe(false);
  });

  it("slskd non configurato (available=false) disabilita «Scarica questo»", async () => {
    jobsMock.useJobs.mockReturnValue({ download: downloadStatus({ available: false }), refresh: vi.fn() });
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    await screen.findByText("Xtal.flac");
    const btn = screen.getAllByText("Scarica questo")[0].closest("button") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("mostra il delta durata rispetto all'attesa", async () => {
    mocks.soulseekSearch.mockResolvedValue({
      variants: [], results: [file({ length: 297 })],
    });
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    // durata attesa 294 (dal review), file 297 -> "+3s vs atteso"
    expect(await screen.findByText(/\+3s/)).toBeTruthy();
  });

  it("scarta la risposta di una ricerca obsoleta che risolve dopo quella piu' recente", async () => {
    let resolveFirst!: (v: { variants: string[]; results: SoulseekSearchFile[] }) => void;
    let resolveSecond!: (v: { variants: string[]; results: SoulseekSearchFile[] }) => void;
    const first = new Promise<{ variants: string[]; results: SoulseekSearchFile[] }>((res) => { resolveFirst = res; });
    const second = new Promise<{ variants: string[]; results: SoulseekSearchFile[] }>((res) => { resolveSecond = res; });
    mocks.soulseekSearch.mockReturnValueOnce(first).mockReturnValueOnce(second);

    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    // Ricerca automatica all'apertura: prima chiamata, resta sospesa (simula il backend lento).
    await waitFor(() => expect(mocks.soulseekSearch).toHaveBeenCalledTimes(1));

    // L'utente riedita la query e ripreme Cerca (invio nel form) prima che la
    // prima risposta arrivi: il pulsante e' disabilitato durante `searching`,
    // ma il campo query resta editabile e il submit del form no.
    const input = screen.getByLabelText("Query di ricerca Soulseek");
    fireEvent.change(input, { target: { value: "Aphex Twin Xtal remix" } });
    fireEvent.submit(input.closest("form")!);
    await waitFor(() => expect(mocks.soulseekSearch).toHaveBeenCalledTimes(2));

    // La seconda ricerca (la piu' recente lanciata) risolve per prima.
    resolveSecond({ variants: [], results: [file({ username: "newer", filename: "newer.flac" })] });
    expect(await screen.findByText("newer.flac")).toBeTruthy();

    // La prima ricerca (obsoleta) risolve dopo: non deve sovrascrivere ne' i
    // risultati mostrati ne' riaccendere lo stato di ricerca.
    resolveFirst({ variants: [], results: [file({ username: "older", filename: "older.flac" })] });
    await waitFor(() => expect(mocks.soulseekSearch).toHaveBeenCalledTimes(2));
    // Lascia fluire i microtask della risposta obsoleta prima di verificare.
    await new Promise((r) => setTimeout(r, 0));

    expect(screen.queryByText("older.flac")).toBeNull();
    expect(screen.getByText("newer.flac")).toBeTruthy();
  });

  it("su errore di ricerca niente empty state, ma il link alla web UI di slskd", async () => {
    // Demone giu': suggerire «prova una variante piu' corta» sarebbe un consiglio
    // sbagliato, e la via d'uscita e' la web UI di slskd (il link della pagina
    // wishlist e' dietro al modal aperto).
    mocks.soulseekSearch.mockRejectedValue(new Error("slskd error: connection refused"));
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    expect(await screen.findByText(/connection refused/)).toBeTruthy();
    expect(screen.queryByText(/Nessun risultato per questa query/)).toBeNull();
    const link = await screen.findByRole("link", { name: /Apri la web UI di slskd/ });
    expect(link.getAttribute("href")).toBe("http://localhost:5030");
  });

  it("blocco Tieni/Scarta presente quando c'e' un file dubbio", async () => {
    mocks.downloadReview.mockResolvedValue({
      expected: { artist: "Aphex Twin", title: "Xtal", duration_seconds: 294 },
      downloaded: { path: "/inbox/x.mp3", name: "x.mp3", format: "mp3", bitrate: 320,
                    duration_seconds: 250, size: 9_000_000 },
      reason: "durata non corrisponde",
    });
    render(<SoulseekSearchModal target={target} onClose={vi.fn()} onPicked={vi.fn()} />);
    expect(await screen.findByText("Tieni comunque")).toBeTruthy();
    expect(screen.getByText("Scarta")).toBeTruthy();
  });
});
