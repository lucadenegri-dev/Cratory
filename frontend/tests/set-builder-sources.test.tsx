import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getManualSet: vi.fn(),
  getMaterial: vi.fn(),
  addSource: vi.fn(),
  removeSource: vi.fn(),
  createManualSet: vi.fn(),
  apiGet: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...api,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
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

const riga = (id: number) => ({
  id, block_id: 1, position: 1, slot_kind: "track" as const, track: track(id),
  note: null, play_bpm: null, planned_seconds: null, alternatives: [],
});

const set = (opts: { revision?: number; sources?: { playlist_id: number; name: string | null }[] } = {}) => ({
  id: 7, name: "Sabato", kind: "manual", revision: opts.revision ?? 1,
  sources: opts.sources ?? [{ playlist_id: 3, name: "Deep" }],
  notes: null, track_count: 1, total_file_seconds: 300,
  can_undo: true, can_redo: false,
  created_at: "2026-09-19T10:00:00", updated_at: "2026-09-19T10:00:00",
  blocks: [{ id: 1, name: null, placement: "main" as const, position: 1, rows: [riga(10)] }],
  reserve: [], transitions: [],
  duration: { seconds: 300, incomplete: false, unknown_rows: 0, open_gaps: 0 },
});

const materiale = () => ({
  sources: [{ playlist_id: 3, name: "Deep" }],
  items: [{ track: track(20), in_set: false, from_playlist: true, in_reserve: false }],
});

beforeEach(() => {
  api.getManualSet.mockResolvedValue(set());
  api.getMaterial.mockResolvedValue(materiale());
  api.apiGet.mockResolvedValue([{ id: 3, name: "Deep" }, { id: 4, name: "Altra" }]);
});
afterEach(() => {
  cleanup();
  Object.values(api).forEach((f) => f.mockReset());
});

describe("le origini del materiale", () => {
  it("compaiono col loro nome", async () => {
    mount();
    const pannello = within(await screen.findByTestId("sources-panel"));
    expect(pannello.getByText("Deep")).toBeTruthy();
  });

  it("aggiungerne una chiama addSource con la revisione", async () => {
    api.addSource.mockResolvedValue(set({ revision: 2 }));
    mount();
    const pannello = within(await screen.findByTestId("sources-panel"));
    fireEvent.change(await pannello.findByLabelText("Aggiungi una playlist"), { target: { value: "4" } });
    await waitFor(() => expect(api.addSource).toHaveBeenCalledWith(7, {
      expected_revision: 1, playlist_id: 4,
    }));
  });

  it("una playlist già scelta non è riproponibile", async () => {
    mount();
    const pannello = within(await screen.findByTestId("sources-panel"));
    await pannello.findByLabelText("Aggiungi una playlist");
    const opzioni = pannello.getAllByRole("option").map((o) => o.textContent);
    expect(opzioni).not.toContain("Deep");
    expect(opzioni).toContain("Altra");
  });

  it("toglierne una chiama removeSource", async () => {
    api.removeSource.mockResolvedValue(set({ revision: 2, sources: [] }));
    mount();
    const pannello = within(await screen.findByTestId("sources-panel"));
    fireEvent.click(pannello.getByTitle("Togli questa origine"));
    await waitFor(() => expect(api.removeSource).toHaveBeenCalledWith(7, 3, 1));
  });

  it("togliere l'ultima origine non svuota il percorso", async () => {
    // Una traccia gia' scelta e' una decisione presa: sparisce dal materiale,
    // non dal set.
    api.removeSource.mockResolvedValue(set({ revision: 2, sources: [] }));
    mount();
    const pannello = within(await screen.findByTestId("sources-panel"));
    fireEvent.click(pannello.getByTitle("Togli questa origine"));
    await waitFor(() => expect(api.removeSource).toHaveBeenCalled());
    expect(within(screen.getByTestId("path-panel")).getByText(/Traccia 10/)).toBeTruthy();
  });
});
