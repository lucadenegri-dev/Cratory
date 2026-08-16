import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import WishlistPage from "@/app/wishlist/page";
import type { DownloadStatus, Track } from "@/lib/api";

afterEach(cleanup);

/* Il «Scarica» di riga non diceva com'era andata: se la deduplica saltava la
   richiesta (traccia già in coda), il click era indistinguibile da uno andato
   a buon fine. La barra di selezione multipla l'esito lo mostrava già, quindi
   la stessa pagina era incoerente con sé stessa. */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
  usePathname: () => "/wishlist",
  useSearchParams: () => new URLSearchParams(),
}));

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  slskdStatus: vi.fn(),
  downloadTrackAuto: vi.fn(),
  enqueueDownloads: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  apiGet: mocks.apiGet,
  slskdStatus: mocks.slskdStatus,
  downloadTrackAuto: mocks.downloadTrackAuto,
  enqueueDownloads: mocks.enqueueDownloads,
}));

const track = (over: Partial<Track> = {}): Track => ({
  id: 1, title: "Real Freak", artist: "Marco Faraone", playlists: [],
  last_download_outcome: null, last_download_reason: null, last_download_path: null,
  has_local_file: false, archived: false,
  ...over,
} as unknown as Track);

const download = (over: Partial<DownloadStatus> = {}): DownloadStatus => ({
  available: true, status: "idle", processed: 0, total: 0, downloaded: 0,
  needs_review: 0, not_found: 0, failed: 0, playlist_id: null, items: [],
  error: null, current_label: null, ...over,
});

const jobsMock = vi.hoisted(() => ({ useJobs: vi.fn() }));
vi.mock("@/components/jobs-provider", () => ({ useJobs: jobsMock.useJobs }));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.apiGet.mockResolvedValue({ total: 1, items: [track()] });
  mocks.slskdStatus.mockResolvedValue({ web_url: null });
  jobsMock.useJobs.mockReturnValue({ download: download(), refresh: vi.fn() });
});

describe("esito dell'accodamento a traccia singola", () => {
  it("accodata: lo dice", async () => {
    mocks.downloadTrackAuto.mockResolvedValue({ enqueued: 1, skipped: 0, replaced: 0 });
    render(<WishlistPage />);
    fireEvent.click(await screen.findByText("Scarica"));
    expect(await screen.findByText("Accodata.")).toBeTruthy();
  });

  it("già in coda: lo dice invece di non dire nulla", async () => {
    mocks.downloadTrackAuto.mockResolvedValue({ enqueued: 0, skipped: 1, replaced: 0 });
    render(<WishlistPage />);
    fireEvent.click(await screen.findByText("Scarica"));
    expect(await screen.findByText(/già in coda/)).toBeTruthy();
  });
});
