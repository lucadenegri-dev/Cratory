import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import WishlistPage from "@/app/wishlist/page";
import type { DownloadStatus, Track } from "@/lib/api";

afterEach(cleanup);

// Con la coda parallela (B) /api/downloads/status resta "running" per tutta
// la vita della coda, non piu' per un singolo download: il vecchio gate
// `available && !running` spegneva TUTTI i bottoni di download appena una
// traccia veniva accodata, cioe' il contrario di quello che serve a una coda.
// Qui si verifica che il bottone resti attivo mentre la coda lavora, e che
// resti invece disabilitato quando slskd non e' proprio configurato.

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
  mocks.downloadQueue.mockResolvedValue({ slots: 1, active: 0, pause: { paused: false }, items: [] });
});

describe("gate dei bottoni di download nella wishlist", () => {
  it("la coda in lavorazione (status=running) non spegne il bottone Scarica", async () => {
    jobsMock.useJobs.mockReturnValue({ download: download({ status: "running" }), refresh: vi.fn() });
    render(<WishlistPage />);
    const btn = await screen.findByText("Scarica");
    expect((btn.closest("button") as HTMLButtonElement).disabled).toBe(false);
  });

  it("slskd non configurato (available=false) disabilita ancora il bottone Scarica", async () => {
    jobsMock.useJobs.mockReturnValue({ download: download({ available: false, status: "idle" }), refresh: vi.fn() });
    render(<WishlistPage />);
    const btn = await screen.findByText("Scarica");
    expect((btn.closest("button") as HTMLButtonElement).disabled).toBe(true);
  });
});
