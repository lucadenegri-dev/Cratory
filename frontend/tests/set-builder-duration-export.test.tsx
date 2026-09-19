import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getManualSet: vi.fn(),
  getMaterial: vi.fn(),
  patchRow: vi.fn(),
  exportManualSet: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...api,
}));

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace: vi.fn() }),
  usePathname: () => "/sets/manual",
  useSearchParams: () => new URLSearchParams("id=7"),
}));

import ManualSetPage from "@/app/sets/manual/page";
import { PlayerProvider } from "@/lib/player";

const mount = () => render(<PlayerProvider><ManualSetPage /></PlayerProvider>);

const track = (id: number) => ({
  id, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
  title: `Traccia ${id}`, artist: "Artista", album: null, genre: null, year: null,
  duration_seconds: 300, bpm: 124, camelot_key: "8A",
  energy: null, label: null, status: "imported", url: null, isrc: null, playlists: [],
  added_at: null, spotify_url: null, album_art_url: null, has_local_file: true, rating: null,
});

const riga = (id: number, position: number) => ({
  id, block_id: 1, position, slot_kind: "track" as const, track: track(id),
  note: null, play_bpm: null, planned_seconds: null, alternatives: [],
});

const set = (opts: { revision?: number; duration?: object } = {}) => ({
  id: 7, name: "Sabato", kind: "manual", revision: opts.revision ?? 1,
  sources: [{ playlist_id: 3, name: "Deep" }], notes: null,
  track_count: 2, total_file_seconds: 600,
  can_undo: true, can_redo: false,
  created_at: "2026-09-19T10:00:00", updated_at: "2026-09-19T10:00:00",
  blocks: [{
    id: 1, name: null, placement: "main" as const, position: 1,
    rows: [riga(10, 1), riga(11, 2)],
  }],
  reserve: [],
  transitions: [],
  duration: {
    seconds: 600, incomplete: false, unknown_rows: 0, open_gaps: 0, ...(opts.duration ?? {}),
  },
});

const material = () => ({
  sources: [{ playlist_id: 3, name: "Deep" }],
  items: [{ track: track(20), in_set: false, from_playlist: true, in_reserve: false }],
});

beforeEach(() => {
  api.getManualSet.mockResolvedValue(set());
  api.getMaterial.mockResolvedValue(material());
});
afterEach(() => {
  cleanup();
  Object.values(api).forEach((f) => f.mockReset());
  push.mockReset();
});

describe("durata", () => {
  it("la mostra in testa", async () => {
    mount();
    // Formato lungo: il totale di un set si legge "2h 14min", non "134:00".
    expect(await screen.findByText(/10 min/)).toBeTruthy();
  });

  it("quando è incompleta dice anche perché", async () => {
    // Una dicitura senza il motivo non basta: il DJ deve sapere COSA manca.
    api.getManualSet.mockResolvedValue(set({
      duration: { incomplete: true, unknown_rows: 1, open_gaps: 2 },
    }));
    mount();
    expect(await screen.findByText(/stima incompleta/)).toBeTruthy();
    expect(screen.getByText(/1 traccia senza durata/)).toBeTruthy();
    expect(screen.getByText(/2 varchi aperti/)).toBeTruthy();
  });
});

describe("export", () => {
  it("l'anteprima mostra esattamente la risposta del server", async () => {
    // Nessuna rielaborazione lato client: e' questo che rende vero
    // «l'anteprima coincide con cio' che esporto».
    api.exportManualSet.mockResolvedValue("# Sabato\n\n- **Artista - Traccia 10**");
    mount();
    fireEvent.click(await screen.findByText("Esporta"));
    fireEvent.click(await screen.findByText("Scheda di preparazione"));
    await waitFor(() => expect(api.exportManualSet).toHaveBeenCalledWith(7, "prep"));
    const anteprima = await screen.findByTestId("export-preview");
    expect(anteprima.textContent).toBe("# Sabato\n\n- **Artista - Traccia 10**");
  });
});
