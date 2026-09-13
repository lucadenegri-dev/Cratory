import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import PlaylistsPage from "@/app/playlists/page";
import type { Playlist } from "@/lib/api";

afterEach(cleanup);

/* Nella lista playlist una playlist senza proprietario stampava «· — ·»: il
   trattino di "valore assente" fra due separatori. Senza owner la voce non
   compare affatto. */

vi.mock("next/navigation", () => ({
  usePathname: () => "/playlists",
}));

const mocks = vi.hoisted(() => ({ listImportedPlaylists: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api")>()),
  listImportedPlaylists: mocks.listImportedPlaylists,
}));

vi.mock("@/components/jobs-provider", () => ({
  useJobs: () => ({ playlistImport: null, refresh: vi.fn(), jobs: [] }),
}));

const playlist = (over: Partial<Playlist> = {}): Playlist => ({
  id: 7, platform: "manual", platform_playlist_id: null, name: "Warm up", owner: null,
  url: null, artwork_url: null, track_count: 3, kind: "manual", name_locked: false,
  imported_at: "2026-09-01T10:00:00Z", ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
});

describe("proprietario nella lista playlist", () => {
  it("senza owner non stampa il trattino", async () => {
    mocks.listImportedPlaylists.mockResolvedValue([playlist()]);
    render(<PlaylistsPage />);
    await screen.findByText("Warm up");
    expect(screen.queryByText(/^·\s*—$/)).toBeNull();
  });

  it("con owner lo mostra", async () => {
    mocks.listImportedPlaylists.mockResolvedValue([playlist({ platform: "spotify", kind: "playlist", owner: "lucadn" })]);
    render(<PlaylistsPage />);
    await screen.findByText("Warm up");
    expect(screen.getByText(/lucadn/)).toBeTruthy();
  });
});
