import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import PlaylistDetailPage from "@/app/playlists/detail/page";
import { PlayerProvider } from "@/lib/player";
import type { Playlist, Track } from "@/lib/api";

afterEach(cleanup);

/* Il dettaglio playlist si apre con la colonna «#» in ordine decrescente: le
   ultime aggiunte in cima, come in libreria. Il trascinamento per riordinare
   resta legato alla vista in ordine naturale («#» crescente), che è a un clic
   sull'intestazione. */

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
}));

vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  getPlaylist: mocks.getPlaylist,
  playlistTracks: mocks.playlistTracks,
  playlistGaps: mocks.playlistGaps,
  playlistSyncLog: mocks.playlistSyncLog,
}));

vi.mock("@/components/jobs-provider", () => ({
  useJobs: () => ({ download: null, refresh: vi.fn() }),
}));

const playlist = (over: Partial<Playlist> = {}): Playlist => ({
  id: 7, platform: "manual", platform_playlist_id: null, name: "Warm up", owner: null,
  url: null, artwork_url: null, track_count: 3, kind: "manual", name_locked: false,
  imported_at: "2026-09-01T10:00:00Z", ...over,
});

const track = (over: Partial<Track> = {}): Track => ({
  id: 1, title: "Prima", artist: "A", playlists: [],
  last_download_outcome: null, last_download_reason: null, last_download_path: null,
  has_local_file: true, archived: false, status: "imported",
  ...over,
} as unknown as Track);

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getPlaylist.mockResolvedValue(playlist());
  // L'array arriva già nell'ordine della playlist: Prima, Seconda, Terza.
  mocks.playlistTracks.mockResolvedValue([
    track({ id: 1, title: "Prima" }),
    track({ id: 2, title: "Seconda" }),
    track({ id: 3, title: "Terza" }),
  ]);
  mocks.playlistGaps.mockResolvedValue(null);
  mocks.playlistSyncLog.mockResolvedValue([]);
});

function renderPage() {
  return render(<PlayerProvider><PlaylistDetailPage /></PlayerProvider>);
}

function titoliInOrdine() {
  return ["Prima", "Seconda", "Terza"]
    .map((x) => screen.getByText(x))
    .sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1))
    .map((el) => el.textContent);
}

describe("ordine iniziale del dettaglio playlist", () => {
  it("si apre con «#» decrescente: l'ultima traccia in cima", async () => {
    renderPage();
    await screen.findByText("Terza");
    expect(titoliInOrdine()).toEqual(["Terza", "Seconda", "Prima"]);
    // La vista è ordinata, quindi il trascinamento è spento.
    expect(screen.getByText("Per riordinare col trascinamento togli filtri e ordinamenti.")).toBeTruthy();
  });

  it("un clic su «#» torna all'ordine naturale e riattiva il trascinamento", async () => {
    renderPage();
    await screen.findByText("Terza");
    fireEvent.click(screen.getByText("#"));
    expect(titoliInOrdine()).toEqual(["Prima", "Seconda", "Terza"]);
    expect(screen.getByText("Trascina le righe per riordinare.")).toBeTruthy();
  });
});
