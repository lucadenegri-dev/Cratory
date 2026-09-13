import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import PlaylistDetailPage from "@/app/playlists/detail/page";
import { PlayerProvider } from "@/lib/player";
import type { DownloadStatus, Playlist, Track } from "@/lib/api";

afterEach(cleanup);

/* La barra di selezione del dettaglio playlist aveva «Aggiungi a playlist» e
   «Togli dalla playlist» ma non «Scarica»: da una playlist si poteva accodare
   o tutte le mancanti o nessuna. Il pulsante accoda le selezionate, ma SOLO
   quelle senza file locale: l'endpoint batch della coda non filtra le
   possedute (lo fa solo la route playlist), quindi il filtro vive qui. */

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  usePathname: () => "/playlists/detail",
  useSearchParams: () => new URLSearchParams("id=7"),
}));

const mocks = vi.hoisted(() => ({
  getPlaylist: vi.fn(),
  playlistTracks: vi.fn(),
  playlistGaps: vi.fn(),
  playlistSyncLog: vi.fn(),
  enqueueDownloads: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getPlaylist: mocks.getPlaylist,
  playlistTracks: mocks.playlistTracks,
  playlistGaps: mocks.playlistGaps,
  playlistSyncLog: mocks.playlistSyncLog,
  enqueueDownloads: mocks.enqueueDownloads,
}));

const jobsMock = vi.hoisted(() => ({ useJobs: vi.fn() }));
vi.mock("@/components/jobs-provider", () => ({ useJobs: jobsMock.useJobs }));

const playlist = (): Playlist => ({
  id: 7, platform: "manual", platform_playlist_id: null, name: "Warm up", owner: null,
  url: null, artwork_url: null, track_count: 3, kind: "manual", name_locked: false,
  imported_at: "2026-09-01T10:00:00Z",
});

const track = (over: Partial<Track> = {}): Track => ({
  id: 1, title: "Real Freak", artist: "Marco Faraone", playlists: [],
  last_download_outcome: null, last_download_reason: null, last_download_path: null,
  has_local_file: false, archived: false, status: "imported",
  ...over,
} as unknown as Track);

const download = (over: Partial<DownloadStatus> = {}): DownloadStatus => ({
  available: true, status: "idle", processed: 0, total: 0, downloaded: 0,
  needs_review: 0, not_found: 0, failed: 0, playlist_id: null, items: [],
  error: null, current_label: null, ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getPlaylist.mockResolvedValue(playlist());
  mocks.playlistTracks.mockResolvedValue([
    track({ id: 1, title: "Mancante uno" }),
    track({ id: 2, title: "Mancante due" }),
    track({ id: 3, title: "Posseduta", has_local_file: true }),
  ]);
  mocks.playlistGaps.mockResolvedValue(null);
  mocks.playlistSyncLog.mockResolvedValue([]);
  mocks.enqueueDownloads.mockResolvedValue({ enqueued: 2, skipped: 0, replaced: 0 });
  jobsMock.useJobs.mockReturnValue({ download: download(), refresh: vi.fn() });
});

function renderPage() {
  return render(<PlayerProvider><PlaylistDetailPage /></PlayerProvider>);
}

async function selectAll() {
  fireEvent.click(await screen.findByLabelText("Seleziona tutte le tracce visibili"));
}

describe("«Scarica» nella barra di selezione del dettaglio playlist", () => {
  it("conta solo le selezionate senza file locale", async () => {
    renderPage();
    await selectAll();
    expect(screen.getByText("Scarica (2)")).toBeTruthy();
  });

  it("accoda solo le mancanti e riporta l'esito", async () => {
    const refresh = vi.fn();
    jobsMock.useJobs.mockReturnValue({ download: download(), refresh });
    renderPage();
    await selectAll();
    fireEvent.click(screen.getByText("Scarica (2)"));
    expect(await screen.findByText("2 accodate")).toBeTruthy();
    expect(mocks.enqueueDownloads).toHaveBeenCalledWith([1, 2]);
    expect(refresh).toHaveBeenCalled();
    // La selezione si svuota: la barra sparisce.
    expect(screen.queryByText("Scarica (2)")).toBeNull();
  });

  it("con sole possedute selezionate il pulsante è spento", async () => {
    renderPage();
    const row = (await screen.findByText("Posseduta")).closest("tr") as HTMLElement;
    fireEvent.click(row.querySelector('input[type="checkbox"]') as HTMLInputElement);
    const btn = screen.getByText("Scarica (0)").closest("button") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });

  it("slskd non configurato spegne il pulsante", async () => {
    jobsMock.useJobs.mockReturnValue({ download: download({ available: false }), refresh: vi.fn() });
    renderPage();
    await selectAll();
    const btn = screen.getByText("Scarica (2)").closest("button") as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});
