import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import WishlistPage from "@/app/wishlist/page";
import type { DownloadStatus, QueueSnapshot, Track } from "@/lib/api";

afterEach(cleanup);

/* Critique 2026-09-06 (P1): una traccia accodata restava «non trovata /
   Riprova», identica a prima del click. L'unico feedback era l'alert
   transitorio. Qui la riga legge lo snapshot della coda e lo dice. Stesso
   giro: tab a conteggio zero nascoste (P2) e «seleziona tutte» in testa
   lista, che rimpiazza «Riprova tutte» della marginalia. */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/wishlist",
  useSearchParams: () => new URLSearchParams(),
}));

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  slskdStatus: vi.fn(),
  downloadQueue: vi.fn(),
  enqueueDownloads: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiGet: mocks.apiGet,
  slskdStatus: mocks.slskdStatus,
  downloadQueue: mocks.downloadQueue,
  enqueueDownloads: mocks.enqueueDownloads,
}));

const jobsMock = vi.hoisted(() => ({ useJobs: vi.fn() }));
vi.mock("@/components/jobs-provider", () => ({ useJobs: jobsMock.useJobs }));

const track = (over: Partial<Track> = {}): Track => ({
  id: 1, title: "Real Freak", artist: "Marco Faraone", playlists: [],
  last_download_outcome: "not_found", last_download_reason: null, last_download_path: null,
  has_local_file: false, archived: false,
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

const queueItem = (track_id: number, state: "queued" | "running") => ({
  id: track_id * 10, track_id, label: "x", kind: "soulseek_auto" as const, state,
  outcome: null, phase: null, bytes_done: null, bytes_total: null, attempts: 0, error: null, position: 0,
});

beforeEach(() => {
  vi.resetAllMocks();
  jobsMock.useJobs.mockReturnValue({ download: download(), refresh: vi.fn() });
  mocks.slskdStatus.mockResolvedValue({ web_url: null });
  mocks.downloadQueue.mockResolvedValue(snapshot());
});

describe("wishlist: stato «in coda» dalla coda", () => {
  it("la riga accodata dice «in coda», con azione e checkbox spente", async () => {
    const t1 = track({ id: 1, title: "Real Freak", artist: "Marco Faraone" });
    const t2 = track({ id: 2, title: "Dark Matter", artist: "Blawan" });
    mocks.apiGet.mockResolvedValue({ total: 2, items: [t1, t2] });
    mocks.downloadQueue.mockResolvedValue(snapshot([queueItem(2, "queued")]));

    render(<WishlistPage />);
    expect(await screen.findByText("in coda")).toBeTruthy();
    // La riga di Blawan e' quella in coda: la sua «Riprova» e' spenta, quella
    // di Faraone no.
    const retries = screen.getAllByText("Riprova").map((el) => el.closest("button") as HTMLButtonElement);
    expect(retries.map((b) => b.disabled)).toEqual([false, true]);
    const boxes = screen.getAllByLabelText("Seleziona questa traccia") as HTMLInputElement[];
    expect(boxes.map((b) => b.disabled)).toEqual([false, true]);
    // Lo stato precedente («non trovata») non compare piu' su quella riga.
    expect(screen.getAllByText("non trovata")).toHaveLength(1);
  });

  it("dopo «Scarica» la coda viene riletta, senza aspettare il poll dei job", async () => {
    const t1 = track({ id: 1, last_download_outcome: null });
    mocks.apiGet.mockResolvedValue({ total: 1, items: [t1] });
    const downloadTrackAuto = vi.fn().mockResolvedValue({ enqueued: 1, skipped: 0, replaced: 0 });
    const api = await import("@/lib/api");
    vi.spyOn(api, "downloadTrackAuto").mockImplementation(downloadTrackAuto);
    mocks.downloadQueue
      .mockResolvedValueOnce(snapshot())
      .mockResolvedValue(snapshot([queueItem(1, "queued")]));

    render(<WishlistPage />);
    fireEvent.click(await screen.findByText("Scarica"));
    expect(await screen.findByText("in coda")).toBeTruthy();
  });
});

describe("wishlist: tab di stato", () => {
  it("le tab a conteggio zero non compaiono; «Tutte» sempre", async () => {
    mocks.apiGet.mockResolvedValue({ total: 1, items: [track({ last_download_outcome: "not_found" })] });
    render(<WishlistPage />);
    await screen.findByText("Marco Faraone — Real Freak");
    expect(screen.getByRole("tab", { name: /Tutte/ })).toBeTruthy();
    expect(screen.getByRole("tab", { name: /Non trovate/ })).toBeTruthy();
    expect(screen.queryByRole("tab", { name: /Fallite/ })).toBeNull();
    expect(screen.queryByRole("tab", { name: /Mai tentate/ })).toBeNull();
  });
});

describe("wishlist: seleziona tutte", () => {
  it("seleziona le righe visibili non in coda e accoda solo quelle", async () => {
    const t1 = track({ id: 1, title: "Real Freak", artist: "Marco Faraone" });
    const t2 = track({ id: 2, title: "Dark Matter", artist: "Blawan" });
    const t3 = track({ id: 3, title: "Xtal", artist: "Aphex Twin" });
    mocks.apiGet.mockResolvedValue({ total: 3, items: [t1, t2, t3] });
    mocks.downloadQueue.mockResolvedValue(snapshot([queueItem(2, "running")]));
    mocks.enqueueDownloads.mockResolvedValue({ enqueued: 2, skipped: 0, replaced: 0 });

    render(<WishlistPage />);
    await screen.findByText("in coda");
    fireEvent.click(screen.getByLabelText("Seleziona tutte le tracce visibili"));
    expect(screen.getByText("2 selezionate")).toBeTruthy();
    fireEvent.click(screen.getByText("Accoda 2 tracce"));
    await waitFor(() => expect(mocks.enqueueDownloads).toHaveBeenCalledWith([1, 3]));
    // Ri-cliccare la testa svuota la selezione.
    await waitFor(() => expect(screen.queryByText(/selezionate/)).toBeNull());
  });

  it("nella vista archiviate non c'e' selezione, quindi nemmeno la testa", async () => {
    mocks.apiGet.mockResolvedValue({ total: 1, items: [track({ archived: true })] });
    render(<WishlistPage />);
    await screen.findByText("Marco Faraone — Real Freak");
    fireEvent.click(screen.getByLabelText("Mostra archiviate"));
    await screen.findByText("Ripristina");
    expect(screen.queryByLabelText("Seleziona tutte le tracce visibili")).toBeNull();
  });
});

describe("wishlist: marginalia", () => {
  it("«Riprova tutte» non c'e' piu'; «Collega tutte» resta", async () => {
    mocks.apiGet.mockResolvedValue({ total: 1, items: [track()] });
    render(<WishlistPage />);
    await screen.findByText("Marco Faraone — Real Freak");
    expect(screen.queryByText("Riprova tutte")).toBeNull();
    expect(screen.getByText("Collega tutte")).toBeTruthy();
  });
});
