import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PlaylistDetailPage from "@/app/playlists/detail/page";
import { PlayerProvider } from "@/lib/player";
import type { Playlist, Track } from "@/lib/api";

afterEach(cleanup);

/* Le playlist di Cratory (manual/shazam) non hanno una cover di piattaforma:
   dal dettaglio l'utente ne carica una. Sulle sincronizzate il comando non
   compare — il backend risponderebbe 409, e la cover e' della piattaforma. */

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
  uploadPlaylistArtwork: vi.fn(),
  deletePlaylistArtwork: vi.fn(),
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getPlaylist: mocks.getPlaylist,
  playlistTracks: mocks.playlistTracks,
  playlistGaps: mocks.playlistGaps,
  playlistSyncLog: mocks.playlistSyncLog,
  uploadPlaylistArtwork: mocks.uploadPlaylistArtwork,
  deletePlaylistArtwork: mocks.deletePlaylistArtwork,
}));

vi.mock("@/components/jobs-provider", () => ({
  useJobs: () => ({ download: null, refresh: vi.fn() }),
}));

const playlist = (over: Partial<Playlist> = {}): Playlist => ({
  id: 7, platform: "manual", platform_playlist_id: null, name: "Warm up", owner: null,
  url: null, artwork_url: null, track_count: 1, kind: "manual", name_locked: false,
  imported_at: "2026-09-01T10:00:00Z", ...over,
});

const track = (): Track => ({
  id: 1, title: "Prima", artist: "A", playlists: [],
  last_download_outcome: null, last_download_reason: null, last_download_path: null,
  has_local_file: true, archived: false, status: "imported",
} as unknown as Track);

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getPlaylist.mockResolvedValue(playlist());
  mocks.playlistTracks.mockResolvedValue([track()]);
  mocks.playlistGaps.mockResolvedValue(null);
  mocks.playlistSyncLog.mockResolvedValue([]);
});

function renderPage() {
  return render(<PlayerProvider><PlaylistDetailPage /></PlayerProvider>);
}

describe("cover caricata dall'utente nel dettaglio playlist", () => {
  it("su una playlist manuale carica il file scelto e mostra la nuova cover", async () => {
    mocks.uploadPlaylistArtwork.mockResolvedValue(playlist({ artwork_url: "/api/playlists/7/artwork?v=42" }));
    renderPage();
    const input = await screen.findByLabelText("Cambia immagine");
    const file = new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "cover.png", { type: "image/png" });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(mocks.uploadPlaylistArtwork).toHaveBeenCalledWith(7, file));
    await waitFor(() => {
      const img = document.querySelector("img[src*='/api/playlists/7/artwork?v=42']");
      expect(img).not.toBeNull();
    });
  });

  it("con una cover caricata offre «Rimuovi immagine»", async () => {
    mocks.getPlaylist.mockResolvedValue(playlist({ artwork_url: "/api/playlists/7/artwork?v=1" }));
    mocks.deletePlaylistArtwork.mockResolvedValue(playlist({ artwork_url: null }));
    renderPage();
    fireEvent.click(await screen.findByText("Rimuovi immagine"));
    await waitFor(() => expect(mocks.deletePlaylistArtwork).toHaveBeenCalledWith(7));
    await waitFor(() => expect(document.querySelector("img[src*='/artwork']")).toBeNull());
  });

  it("su una playlist sincronizzata il comando non compare", async () => {
    mocks.getPlaylist.mockResolvedValue(playlist({ platform: "spotify", kind: "playlist", artwork_url: "https://i.scdn.co/x.jpg" }));
    renderPage();
    await screen.findByRole("heading", { name: "Warm up" });
    expect(screen.queryByLabelText("Cambia immagine")).toBeNull();
  });

  it("un upload rifiutato lo dice", async () => {
    mocks.uploadPlaylistArtwork.mockRejectedValue(new Error("Only PNG, JPEG and WebP images are accepted."));
    renderPage();
    const input = await screen.findByLabelText("Cambia immagine");
    fireEvent.change(input, { target: { files: [new File(["x"], "x.txt", { type: "text/plain" })] } });
    expect(await screen.findByText(/Only PNG/)).toBeTruthy();
  });
});
