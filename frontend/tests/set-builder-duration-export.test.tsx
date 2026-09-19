import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

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

const riga = (id: number, position: number, planned: number | null = null) => ({
  id, block_id: 1, position, slot_kind: "track" as const, track: track(id),
  note: null, play_bpm: null, planned_seconds: planned, alternatives: [],
});

const set = (opts: { revision?: number; duration?: object; planned?: number | null } = {}) => ({
  id: 7, name: "Sabato", kind: "manual", revision: opts.revision ?? 1,
  source_playlist_id: 3, source_playlist_name: "Deep", notes: null,
  track_count: 2, total_file_seconds: 600,
  can_undo: true, can_redo: false,
  created_at: "2026-09-19T10:00:00", updated_at: "2026-09-19T10:00:00",
  blocks: [{
    id: 1, name: null, placement: "main" as const, position: 1,
    rows: [riga(10, 1, opts.planned ?? null), riga(11, 2)],
  }],
  reserve: [],
  transitions: [],
  duration: {
    seconds: 600, incomplete: false, unknown_rows: 0, open_gaps: 0, ...(opts.duration ?? {}),
  },
});

const material = () => ({
  playlist_id: 3, playlist_name: "Deep",
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

const seleziona = async (id: number) => {
  const li = (await screen.findByTestId("path-panel")).querySelector(`li[data-row="${id}"]`);
  fireEvent.click(within(li as HTMLElement).getByRole("button", { name: /Traccia/ }));
};

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

describe("«quanto la tengo»", () => {
  it("manda solo planned_seconds", async () => {
    api.patchRow.mockResolvedValue(set({ revision: 2, planned: 120 }));
    mount();
    await seleziona(10);
    const campo = within(screen.getByTestId("detail-panel")).getByLabelText("Quanto la tengo");
    fireEvent.change(campo, { target: { value: "120" } });
    fireEvent.blur(campo);
    await waitFor(() => expect(api.patchRow).toHaveBeenCalledWith(7, 10, {
      expected_revision: 1, planned_seconds: 120,
    }));
  });

  it("svuotare il campo azzera la durata pianificata", async () => {
    api.getManualSet.mockResolvedValue(set({ planned: 120 }));
    api.patchRow.mockResolvedValue(set({ revision: 2 }));
    mount();
    await seleziona(10);
    const campo = within(screen.getByTestId("detail-panel")).getByLabelText("Quanto la tengo");
    fireEvent.change(campo, { target: { value: "" } });
    fireEvent.blur(campo);
    await waitFor(() => expect(api.patchRow).toHaveBeenCalledWith(7, 10, {
      expected_revision: 1, planned_seconds: null,
    }));
  });

  it("un valore invariato non chiama niente", async () => {
    api.getManualSet.mockResolvedValue(set({ planned: 120 }));
    mount();
    await seleziona(10);
    const campo = within(screen.getByTestId("detail-panel")).getByLabelText("Quanto la tengo");
    fireEvent.blur(campo);
    expect(api.patchRow).not.toHaveBeenCalled();
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
