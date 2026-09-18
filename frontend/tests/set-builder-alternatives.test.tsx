import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getManualSet: vi.fn(),
  getMaterial: vi.fn(),
  insertRows: vi.fn(),
  moveRow: vi.fn(),
  patchRow: vi.fn(),
  removeRow: vi.fn(),
  addAlternatives: vi.fn(),
  removeAlternative: vi.fn(),
  chooseAlternative: vi.fn(),
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

const track = (id: number, extra = {}) => ({
  id, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
  title: `Traccia ${id}`, artist: "Artista", album: null, genre: null, year: null,
  duration_seconds: 300, bpm: id === 3 ? null : 124, camelot_key: id === 3 ? null : "8A",
  energy: null, label: null, status: "imported", url: null, isrc: null, playlists: [],
  added_at: null, spotify_url: null, album_art_url: null, has_local_file: true, rating: null, ...extra,
});

const alt = (id: number, trackId: number) => ({ id, position: id, track: track(trackId), note: null });

const set = (opts: { revision?: number; alts?: number[]; reserve?: number[] } = {}) => ({
  id: 7, name: "Sabato", kind: "manual", revision: opts.revision ?? 1,
  source_playlist_id: 3, source_playlist_name: "Deep", notes: null,
  track_count: 1, total_file_seconds: 300,
  created_at: "2026-09-19T10:00:00", updated_at: "2026-09-19T10:00:00",
  blocks: [{
    id: 1, name: null, placement: "main" as const, position: 1,
    rows: [{
      id: 10, block_id: 1, position: 1, slot_kind: "track" as const, track: track(1), note: null,
      alternatives: (opts.alts ?? []).map((tid, i) => alt(i + 1, tid)),
    }],
  }],
  reserve: (opts.reserve ?? []).map((tid, i) => ({
    id: 90 + i, block_id: null, position: i + 1, slot_kind: "track" as const,
    track: track(tid), note: null, alternatives: [],
  })),
});

const material = () => ({
  playlist_id: 3, playlist_name: "Deep",
  items: [1, 2, 3].map((id) => ({
    track: track(id), in_set: id === 1, from_playlist: true, in_reserve: false,
  })),
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

const selezionaLaRiga = async () => {
  const titoli = await screen.findAllByText(/Traccia 1/);
  fireEvent.click(titoli.find((el) => el.closest("button"))!);
};

/** Il comando `titolo` sulla riga di materiale della traccia `n`: il pannello
 *  li mostra su ogni riga, quindi prendere il primo del documento colpirebbe
 *  la traccia sbagliata. */
const comandoSuMateriale = (n: number, titolo: string) => {
  const riga = screen.getByTestId("material-panel")
    .querySelectorAll("li");
  const target = Array.from(riga).find((li) => li.textContent?.includes(`Traccia ${n}`));
  return within(target as HTMLElement).getByTitle(titolo);
};

describe("alternative", () => {
  it("tiene una traccia del materiale come alternativa della riga selezionata", async () => {
    api.addAlternatives.mockResolvedValue(set({ revision: 2, alts: [2] }));
    mount();
    await selezionaLaRiga();
    fireEvent.click(comandoSuMateriale(2, "Tieni come alternativa"));
    await waitFor(() => expect(api.addAlternatives).toHaveBeenCalledWith(7, 10, {
      expected_revision: 1, track_ids: [2],
    }));
  });

  it("«Usa» scambia l'attiva con la candidata scelta", async () => {
    api.getManualSet.mockResolvedValue(set({ alts: [2] }));
    api.chooseAlternative.mockResolvedValue(set({ revision: 2, alts: [1] }));
    mount();
    await selezionaLaRiga();
    const dettaglio = within(screen.getByTestId("detail-panel"));
    fireEvent.click(dettaglio.getByText("Usa"));
    await waitFor(() => expect(api.chooseAlternative).toHaveBeenCalledWith(7, 10, 1, {
      expected_revision: 1,
    }));
  });

  it("toglie una candidata dalla riga", async () => {
    api.getManualSet.mockResolvedValue(set({ alts: [2] }));
    api.removeAlternative.mockResolvedValue(set({ revision: 2 }));
    mount();
    await selezionaLaRiga();
    const dettaglio = within(screen.getByTestId("detail-panel"));
    fireEvent.click(dettaglio.getByTitle("Togli dalle alternative"));
    await waitFor(() => expect(api.removeAlternative).toHaveBeenCalledWith(7, 10, 1, 1));
  });

  it("il confronto mostra le candidate con «sconosciuto» sui dati mancanti", async () => {
    api.getManualSet.mockResolvedValue(set({ alts: [2, 3] }));
    mount();
    await selezionaLaRiga();
    fireEvent.click(screen.getByText(/Confronta le 3/));
    const confronto = within(await screen.findByTestId("compare-panel"));
    expect(confronto.getAllByText(/Traccia/).length).toBe(3);
    // La terza candidata non ha né BPM né tonalità: due "sconosciuto".
    expect(confronto.getAllByText("sconosciuto").length).toBe(2);
  });
});

describe("riserva", () => {
  it("mette da parte una traccia del materiale", async () => {
    api.insertRows.mockResolvedValue(set({ revision: 2, reserve: [2] }));
    mount();
    await screen.findAllByText(/Traccia 2/);
    fireEvent.click(comandoSuMateriale(2, "Metti da parte per la serata"));
    await waitFor(() => expect(api.insertRows).toHaveBeenCalledWith(7, {
      expected_revision: 1, track_ids: [2], reserve: true,
    }));
  });

  it("rimette nel percorso una traccia della riserva", async () => {
    api.getManualSet.mockResolvedValue(set({ reserve: [2] }));
    api.moveRow.mockResolvedValue(set({ revision: 2 }));
    mount();
    const riserva = within(await screen.findByTestId("reserve-panel"));
    fireEvent.click(riserva.getByTitle("Rimetti nel percorso"));
    await waitFor(() => expect(api.moveRow).toHaveBeenCalledWith(7, 90, {
      expected_revision: 1, position: 1, to_reserve: false,
    }));
  });

  it("cambiare i filtri del materiale non ferma ciò che sta suonando", async () => {
    // Verifica dichiarata dalla spec per questa tappa: il contesto di ascolto è
    // uno snapshot preso all'avvio, filtrare la lista non lo tocca.
    api.getManualSet.mockResolvedValue(set({ reserve: [2] }));
    mount();
    await screen.findAllByText(/Traccia 1/);
    fireEvent.click(screen.getAllByLabelText("Ascolta")[0]);
    const inAscolto = await screen.findAllByLabelText("Ferma");
    expect(inAscolto.length).toBe(1);

    fireEvent.click(screen.getByText("da parte"));
    await waitFor(() => expect(api.getMaterial).toHaveBeenCalledWith(
      7, expect.objectContaining({ reserved: true }),
    ));
    // Stessa traccia ancora in riproduzione: nessun "Ascolta" al suo posto.
    expect(screen.getAllByLabelText("Ferma").length).toBe(1);
  });
});
