import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import PlaylistDetailPage from "@/app/playlists/detail/page";
import { PlayerProvider } from "@/lib/player";
import type { Playlist, Track } from "@/lib/api";

afterEach(cleanup);

/* La key nel dettaglio playlist: il filtro cerca la key Camelot esatta (non
   una sottostringa: "1A" non è "11A"). */

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
  id: 1, title: "Prima", artist: "A", playlists: [], camelot_key: null,
  last_download_outcome: null, last_download_reason: null, last_download_path: null,
  has_local_file: true, archived: false, status: "imported",
  ...over,
} as unknown as Track);

beforeEach(() => {
  vi.clearAllMocks();
  mocks.getPlaylist.mockResolvedValue(playlist());
  mocks.playlistGaps.mockResolvedValue(null);
  mocks.playlistSyncLog.mockResolvedValue([]);
});

function renderPage() {
  return render(<PlayerProvider><PlaylistDetailPage /></PlayerProvider>);
}

/** I titoli presenti fra `titles`, nell'ordine in cui compaiono nella pagina. */
function titoliInOrdine(titles: string[]) {
  return titles
    .flatMap((x) => screen.queryAllByText(x))
    .sort((a, b) => (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1))
    .map((el) => el.textContent);
}

describe("filtro per key del dettaglio playlist", () => {
  const titles = ["Uno", "Undici", "Minuscola"];

  beforeEach(() => {
    mocks.playlistTracks.mockResolvedValue([
      track({ id: 1, title: "Uno", camelot_key: "1A" }),
      track({ id: 2, title: "Undici", camelot_key: "11A" }),
      track({ id: 3, title: "Minuscola", camelot_key: " 1a " }),
    ]);
  });

  it("«1A» trova solo 1A, non 11A", async () => {
    renderPage();
    await screen.findByText("Undici");
    fireEvent.change(screen.getByPlaceholderText("Key (es. 7A)"), { target: { value: "1A" } });
    expect(titoliInOrdine(titles).sort()).toEqual(["Minuscola", "Uno"]);
  });

  it("maiuscole e spazi nella ricerca non contano", async () => {
    renderPage();
    await screen.findByText("Undici");
    fireEvent.change(screen.getByPlaceholderText("Key (es. 7A)"), { target: { value: " 1a" } });
    expect(titoliInOrdine(titles).sort()).toEqual(["Minuscola", "Uno"]);
  });
});

