import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getManualSet: vi.fn(),
  getMaterial: vi.fn(),
  insertRows: vi.fn(),
  moveRow: vi.fn(),
  patchRow: vi.fn(),
  removeRow: vi.fn(),
  setPairNote: vi.fn(),
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

const track = (id: number, bpm: number | null = 124) => ({
  id, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
  title: `Traccia ${id}`, artist: "Artista", album: null, genre: null, year: null,
  duration_seconds: 300, bpm, camelot_key: "8A",
  energy: null, label: null, status: "imported", url: null, isrc: null, playlists: [],
  added_at: null, spotify_url: null, album_art_url: null, has_local_file: true, rating: null,
});

const riga = (id: number, position: number, playBpm: number | null = null) => ({
  id, block_id: 1, position, slot_kind: "track" as const, track: track(id),
  note: null, play_bpm: playBpm, alternatives: [],
});

const passaggio = (extra = {}) => ({
  from_row_id: 10, to_row_id: 11, from_track_id: 10, to_track_id: 11,
  bpm_from: 124, bpm_to: 126, bpm_percent: 1.6, halftime: false,
  key_from: "8A", key_to: "9A", key_relation: "adjacent" as const,
  score: 82, missing: [] as string[], note: null as string | null, ...extra,
});

const set = (opts: { revision?: number; transition?: object; playBpm?: number | null } = {}) => ({
  id: 7, name: "Sabato", kind: "manual", revision: opts.revision ?? 1,
  source_playlist_id: 3, source_playlist_name: "Deep", notes: null,
  track_count: 2, total_file_seconds: 600,
  can_undo: true, can_redo: false,
  created_at: "2026-09-19T10:00:00", updated_at: "2026-09-19T10:00:00",
  blocks: [{
    id: 1, name: null, placement: "main" as const, position: 1,
    rows: [riga(10, 1, opts.playBpm ?? null), riga(11, 2)],
  }],
  reserve: [],
  transitions: [passaggio(opts.transition ?? {})],
});

const material = () => ({
  playlist_id: 3, playlist_name: "Deep",
  items: [20].map((id) => ({
    track: track(id), in_set: false, from_playlist: true, in_reserve: false,
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

/** Seleziona la riga `id` nel percorso: il dettaglio mostra i suoi passaggi. */
const seleziona = async (id: number) => {
  const li = (await screen.findByTestId("path-panel")).querySelector(`li[data-row="${id}"]`);
  fireEvent.click(within(li as HTMLElement).getByRole("button", { name: /Traccia/ }));
};

describe("il passaggio", () => {
  it("mostra i due tempi e il pitch che serve", async () => {
    mount();
    await seleziona(10);
    const uscita = within(await screen.findByTestId("transition-panel-out"));
    expect(uscita.getByText(/124/)).toBeTruthy();
    expect(uscita.getByText(/126/)).toBeTruthy();
    expect(uscita.getByText(/1[.,]6/)).toBeTruthy();
  });

  it("sulla riga dopo compare il passaggio in entrata, non quello in uscita", async () => {
    mount();
    await seleziona(11);
    expect(await screen.findByTestId("transition-panel-in")).toBeTruthy();
    expect(screen.queryByTestId("transition-panel-out")).toBeNull();
  });

  it("un dato mancante si legge «sconosciuto», e nessun punteggio", async () => {
    api.getManualSet.mockResolvedValue(set({
      transition: { bpm_from: null, bpm_percent: null, score: null, missing: ["bpm"] },
    }));
    mount();
    await seleziona(10);
    const uscita = within(await screen.findByTestId("transition-panel-out"));
    expect(uscita.getAllByText("sconosciuto").length).toBeGreaterThan(0);
    expect(uscita.queryByText(/82/)).toBeNull();
  });

  it("l'appunto del passaggio si salva sulle due tracce", async () => {
    api.setPairNote.mockResolvedValue(set({ revision: 2 }));
    mount();
    await seleziona(10);
    const campo = within(await screen.findByTestId("transition-panel-out"))
      .getByPlaceholderText("Come ci entro, cosa taglio…");
    fireEvent.change(campo, { target: { value: "entra sul break" } });
    fireEvent.blur(campo);
    await waitFor(() => expect(api.setPairNote).toHaveBeenCalledWith(7, {
      expected_revision: 1, from_track_id: 10, to_track_id: 11, note: "entra sul break",
    }));
  });

  it("un appunto invariato non chiama niente", async () => {
    api.getManualSet.mockResolvedValue(set({ transition: { note: "già scritto" } }));
    mount();
    await seleziona(10);
    const campo = within(await screen.findByTestId("transition-panel-out"))
      .getByPlaceholderText("Come ci entro, cosa taglio…");
    fireEvent.blur(campo);
    expect(api.setPairNote).not.toHaveBeenCalled();
  });
});

describe("«la suono a»", () => {
  it("manda solo play_bpm, senza toccare l'appunto", async () => {
    // Il corpo deve contenere la sola proprietà toccata: mandare anche `note`
    // la riscriverebbe a ogni salvataggio del tempo.
    api.patchRow.mockResolvedValue(set({ revision: 2, playBpm: 126 }));
    mount();
    await seleziona(10);
    const campo = within(screen.getByTestId("detail-panel")).getByLabelText("La suono a");
    fireEvent.change(campo, { target: { value: "126" } });
    fireEvent.blur(campo);
    await waitFor(() => expect(api.patchRow).toHaveBeenCalledWith(7, 10, {
      expected_revision: 1, play_bpm: 126,
    }));
  });

  it("svuotare il campo azzera il tempo di cabina", async () => {
    api.getManualSet.mockResolvedValue(set({ playBpm: 126 }));
    api.patchRow.mockResolvedValue(set({ revision: 2 }));
    mount();
    await seleziona(10);
    const campo = within(screen.getByTestId("detail-panel")).getByLabelText("La suono a");
    fireEvent.change(campo, { target: { value: "" } });
    fireEvent.blur(campo);
    await waitFor(() => expect(api.patchRow).toHaveBeenCalledWith(7, 10, {
      expected_revision: 1, play_bpm: null,
    }));
  });

  it("un valore invariato non chiama niente", async () => {
    api.getManualSet.mockResolvedValue(set({ playBpm: 126 }));
    mount();
    await seleziona(10);
    const campo = within(screen.getByTestId("detail-panel")).getByLabelText("La suono a");
    fireEvent.blur(campo);
    expect(api.patchRow).not.toHaveBeenCalled();
  });
});
