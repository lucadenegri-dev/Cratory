import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getManualSet: vi.fn(),
  getMaterial: vi.fn(),
  fillGap: vi.fn(),
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

import { ApiError } from "@/lib/api";
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

const varco = (id: number, position: number) => ({
  id, block_id: 1, position, slot_kind: "gap" as const, track: null,
  note: null, play_bpm: null, planned_seconds: null, alternatives: [],
});

/** Due tracce con un varco in mezzo. */
const set = (opts: { revision?: number } = {}) => ({
  id: 7, name: "Sabato", kind: "manual", revision: opts.revision ?? 1,
  sources: [{ playlist_id: 3, name: "Deep" }], notes: null,
  track_count: 2, total_file_seconds: 600,
  can_undo: true, can_redo: false,
  created_at: "2026-09-19T10:00:00", updated_at: "2026-09-19T10:00:00",
  blocks: [{
    id: 1, name: null, placement: "main" as const, position: 1,
    rows: [riga(10, 1), varco(11, 2), riga(12, 3)],
  }],
  reserve: [],
  transitions: [],
  duration: { seconds: 600, incomplete: true, unknown_rows: 0, open_gaps: 1 },
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

const rigaDi = (id: number) =>
  screen.getByTestId("path-panel").querySelector(`li[data-row="${id}"]`) as HTMLElement;

describe("riempi il varco", () => {
  it("il comando c'è solo sulla riga del varco", async () => {
    mount();
    await screen.findByTestId("path-panel");
    expect(within(rigaDi(11)).getByTitle("Riempi il varco")).toBeTruthy();
    expect(within(rigaDi(10)).queryByTitle("Riempi il varco")).toBeNull();
  });

  it("chiama fillGap con l'id del varco e il numero scelto", async () => {
    api.fillGap.mockResolvedValue(set({ revision: 2 }));
    mount();
    await screen.findByTestId("path-panel");
    fireEvent.click(within(rigaDi(11)).getByTitle("Riempi il varco"));
    const pannello = within(await screen.findByTestId("fill-gap"));
    fireEvent.change(pannello.getByLabelText("Quante tracce"), { target: { value: "3" } });
    fireEvent.click(pannello.getByText("Riempi"));
    await waitFor(() => expect(api.fillGap).toHaveBeenCalledWith(7, 11, {
      expected_revision: 1, count: 3,
    }));
  });

  it("un rifiuto del generatore si vede, e il varco resta aperto", async () => {
    // `handle` in lib/api/client.ts traduce il codice PRIMA di costruire
    // l'ApiError: il messaggio che la pagina mostra e' gia' quello italiano.
    api.fillGap.mockRejectedValue(new ApiError(
      "Il generatore non è riuscito a riempire questo varco", 422, "set_fill_failed"));
    mount();
    await screen.findByTestId("path-panel");
    fireEvent.click(within(rigaDi(11)).getByTitle("Riempi il varco"));
    fireEvent.click(within(await screen.findByTestId("fill-gap")).getByText("Riempi"));
    expect(await screen.findByText(/non è riuscito a riempire/)).toBeTruthy();
    // Il percorso non e' cambiato: il varco e' ancora li'.
    expect(rigaDi(11)).toBeTruthy();
  });
});
