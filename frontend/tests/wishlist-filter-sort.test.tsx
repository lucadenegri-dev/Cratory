import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import WishlistPage from "@/app/wishlist/page";
import type { DownloadStatus, QueueSnapshot, Track } from "@/lib/api";

afterEach(cleanup);

/* Aggiunte del 2026-09-06: lo stato «in coda» diventa filtrabile come gli
   altri (prima le righe lo dicevano e basta), la data di aggiunta compare
   accanto alla provenienza e la lista si può ordinare per quella data. */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/wishlist",
  useSearchParams: () => new URLSearchParams(),
}));

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  slskdStatus: vi.fn(),
  downloadQueue: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiGet: mocks.apiGet,
  slskdStatus: mocks.slskdStatus,
  downloadQueue: mocks.downloadQueue,
}));

const jobsMock = vi.hoisted(() => ({ useJobs: vi.fn() }));
vi.mock("@/components/jobs-provider", () => ({ useJobs: jobsMock.useJobs }));

const track = (over: Partial<Track> = {}): Track => ({
  id: 1, title: "Real Freak", artist: "Marco Faraone", playlists: [],
  last_download_outcome: "not_found", last_download_reason: null, last_download_path: null,
  has_local_file: false, archived: false, added_at: null,
  ...over,
} as unknown as Track);

const download = (over: Partial<DownloadStatus> = {}): DownloadStatus => ({
  available: true, status: "idle", processed: 0, total: 0, downloaded: 0,
  needs_review: 0, not_found: 0, failed: 0, playlist_id: null, items: [],
  error: null, current_label: null, ...over,
});

const snapshot = (items: QueueSnapshot["items"] = []): QueueSnapshot => ({
  slots: 2, active: 0, pause: { paused: false, reason: null, retry_in_seconds: null }, items,
});

const queueItem = (track_id: number) => ({
  id: track_id * 10, track_id, label: "x", kind: "soulseek_auto" as const, state: "queued" as const,
  outcome: null, phase: null, bytes_done: null, bytes_total: null, attempts: 0, error: null, position: 0,
});

// Il primo <a> della riga e' quello della copertina (aria-hidden, senza
// testo): il titolo e' il primo link con del testo dentro.
const titles = () => [...document.querySelectorAll("li")]
  .map((li) => [...li.querySelectorAll("a")].map((a) => a.textContent).find(Boolean) ?? "")
  .filter(Boolean);

beforeEach(() => {
  vi.resetAllMocks();
  jobsMock.useJobs.mockReturnValue({ download: download(), refresh: vi.fn() });
  mocks.slskdStatus.mockResolvedValue({ web_url: null });
  mocks.downloadQueue.mockResolvedValue(snapshot());
});

describe("wishlist: «in coda» è uno stato filtrabile", () => {
  const setup = () => {
    const t1 = track({ id: 1, artist: "Aaa", title: "Non trovata" });
    const t2 = track({ id: 2, artist: "Bbb", title: "In coda" });
    const t3 = track({ id: 3, artist: "Ccc", title: "Da rivedere", last_download_outcome: "needs_review" });
    mocks.apiGet.mockResolvedValue({ total: 3, items: [t1, t2, t3] });
    mocks.downloadQueue.mockResolvedValue(snapshot([queueItem(2)]));
  };

  it("la tab compare col suo conteggio e isola le righe in coda", async () => {
    setup();
    render(<WishlistPage />);
    expect(await screen.findByRole("tab", { name: /In coda\s*1/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: /In coda/ }));
    expect(titles()).toEqual(["Bbb — In coda"]);
  });

  it("una traccia in coda esce dalla tab del suo vecchio esito: conteggio e righe concordano", async () => {
    setup();
    render(<WishlistPage />);
    // Due tracce hanno esito "not_found" (t1 e t2), ma t2 e' in coda: la tab
    // «Non trovate» ne conta una sola, ed e' quella che mostra.
    expect(await screen.findByRole("tab", { name: /Non trovate\s*1/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: /Non trovate/ }));
    expect(titles()).toEqual(["Aaa — Non trovata"]);
  });

  it("senza nulla in coda la tab non compare (come le altre a zero)", async () => {
    mocks.apiGet.mockResolvedValue({ total: 1, items: [track()] });
    render(<WishlistPage />);
    await screen.findByText("Marco Faraone — Real Freak");
    expect(screen.queryByRole("tab", { name: /In coda/ })).toBeNull();
  });
});

describe("wishlist: data di aggiunta e ordinamento", () => {
  const DATED = [
    track({ id: 1, artist: "Aaa", title: "Vecchia", added_at: "2026-01-15T10:00:00" }),
    track({ id: 2, artist: "Bbb", title: "Recente", added_at: "2026-08-09T12:12:43" }),
    track({ id: 3, artist: "Ccc", title: "Senza data", added_at: null }),
  ];

  it("la data compare accanto alla provenienza, e chi non ce l'ha non mostra nulla", async () => {
    mocks.apiGet.mockResolvedValue({ total: 3, items: DATED });
    render(<WishlistPage />);
    await screen.findByText("Aaa — Vecchia");
    const rows = [...document.querySelectorAll("li")];
    expect(rows[0].textContent).toMatch(/\d{2}\/\d{2}\/\d{2}/);
    expect(rows[1].textContent).toMatch(/\d{2}\/\d{2}\/\d{2}/);
    expect(rows[2].textContent).not.toMatch(/\d{2}\/\d{2}\/\d{2}/);
  });

  it("ordina per data, con le tracce senza data in fondo in entrambi i versi", async () => {
    mocks.apiGet.mockResolvedValue({ total: 3, items: DATED });
    render(<WishlistPage />);
    await screen.findByText("Aaa — Vecchia");
    const sort = screen.getByLabelText("Ordina la lista");

    fireEvent.change(sort, { target: { value: "added_desc" } });
    expect(titles()).toEqual(["Bbb — Recente", "Aaa — Vecchia", "Ccc — Senza data"]);

    fireEvent.change(sort, { target: { value: "added_asc" } });
    expect(titles()).toEqual(["Aaa — Vecchia", "Bbb — Recente", "Ccc — Senza data"]);

    // Tornando ad artista si riprende l'ordine servito dall'API (sort=artist).
    fireEvent.change(sort, { target: { value: "artist" } });
    expect(titles()).toEqual(["Aaa — Vecchia", "Bbb — Recente", "Ccc — Senza data"]);
  });

  it("l'ordinamento non tocca la selezione: le stesse righe restano visibili", async () => {
    mocks.apiGet.mockResolvedValue({ total: 3, items: DATED });
    render(<WishlistPage />);
    const boxes = await screen.findAllByLabelText("Seleziona questa traccia");
    fireEvent.click(boxes[0]);
    expect(screen.getByText("1 selezionata")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Ordina la lista"), { target: { value: "added_desc" } });
    expect(screen.getByText("1 selezionata")).toBeTruthy();
  });
});
