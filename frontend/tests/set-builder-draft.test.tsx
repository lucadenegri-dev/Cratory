import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getManualSet: vi.fn(),
  getMaterial: vi.fn(),
  draftMaterial: vi.fn(),
  createManualSet: vi.fn(),
  insertRows: vi.fn(),
  addSource: vi.fn(),
  apiGet: vi.fn(),
}));
vi.mock("@/lib/api", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  ...api,
}));

const push = vi.fn();
const replace = vi.fn();
const query = vi.hoisted(() => ({ value: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push, replace }),
  usePathname: () => "/sets/manual",
  useSearchParams: () => new URLSearchParams(query.value),
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

const setSalvato = () => ({
  id: 9, name: "Sabato", kind: "manual", revision: 1,
  sources: [{ playlist_id: 3, name: "Deep" }], notes: null,
  track_count: 0, total_file_seconds: 0,
  can_undo: true, can_redo: false,
  created_at: "2026-09-19T10:00:00", updated_at: "2026-09-19T10:00:00",
  blocks: [{ id: 1, name: null, placement: "main" as const, position: 1, rows: [] }],
  reserve: [], transitions: [],
  duration: { seconds: 0, incomplete: false, unknown_rows: 0, open_gaps: 0 },
});

const materiale = () => ({
  sources: [{ playlist_id: 3, name: "Deep" }],
  items: [{ track: track(20), in_set: false, from_playlist: true, in_reserve: false }],
});

beforeEach(() => {
  query.value = "";                       // nessun ?id=: è una bozza
  api.draftMaterial.mockResolvedValue(materiale());
  api.getMaterial.mockResolvedValue(materiale());
  api.getManualSet.mockResolvedValue(setSalvato());
  api.apiGet.mockResolvedValue([{ id: 3, name: "Deep" }, { id: 4, name: "Altra" }]);
});
afterEach(() => {
  cleanup();
  Object.values(api).forEach((f) => f.mockReset());
  push.mockReset();
  replace.mockReset();
});

describe("la bozza", () => {
  it("all'apertura non salva niente: nessun set creato, nessun set letto", async () => {
    mount();
    await screen.findByTestId("sources-panel");
    expect(api.createManualSet).not.toHaveBeenCalled();
    expect(api.getManualSet).not.toHaveBeenCalled();
    expect(api.draftMaterial).toHaveBeenCalled();
  });

  it("scegliere una playlist non crea il set: cambia solo il materiale", async () => {
    mount();
    const pannello = within(await screen.findByTestId("sources-panel"));
    fireEvent.change(await pannello.findByLabelText("Aggiungi una playlist"), { target: { value: "4" } });
    await waitFor(() => expect(api.draftMaterial).toHaveBeenCalledWith(
      expect.objectContaining({ playlist_ids: [4] })));
    expect(api.createManualSet).not.toHaveBeenCalled();
    expect(api.addSource).not.toHaveBeenCalled();
  });

  it("la prima traccia crea il set, e SOLO POI la inserisce", async () => {
    api.createManualSet.mockResolvedValue(setSalvato());
    api.insertRows.mockResolvedValue(setSalvato());
    mount();
    const pannello = within(await screen.findByTestId("sources-panel"));
    fireEvent.change(await pannello.findByLabelText("Aggiungi una playlist"), { target: { value: "3" } });
    await screen.findByTestId("material-panel");

    fireEvent.click(within(screen.getByTestId("material-panel")).getAllByTitle("Aggiungi al percorso")[0]);

    await waitFor(() => expect(api.insertRows).toHaveBeenCalled());
    expect(api.createManualSet).toHaveBeenCalledWith({ playlist_ids: [3] });
    // L'ordine conta: se il set nascesse DOPO, l'inserimento andrebbe nel vuoto.
    expect(api.createManualSet.mock.invocationCallOrder[0])
      .toBeLessThan(api.insertRows.mock.invocationCallOrder[0]);
  });

  it("appena il set nasce, l'URL prende il suo id", async () => {
    api.createManualSet.mockResolvedValue(setSalvato());
    api.insertRows.mockResolvedValue(setSalvato());
    mount();
    await screen.findByTestId("material-panel");
    fireEvent.click(within(screen.getByTestId("material-panel")).getAllByTitle("Aggiungi al percorso")[0]);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/sets/manual?id=9"));
  });

  it("con un id in query il set c'è già: non se ne crea un altro", async () => {
    query.value = "id=7";
    mount();
    await screen.findByTestId("material-panel");
    expect(api.getManualSet).toHaveBeenCalledWith(7);
    expect(api.createManualSet).not.toHaveBeenCalled();
  });

  it("«?playlist=» arriva già scelta nella bozza", async () => {
    query.value = "playlist=4";
    mount();
    await waitFor(() => expect(api.draftMaterial).toHaveBeenCalledWith(
      expect.objectContaining({ playlist_ids: [4] })));
  });
});
