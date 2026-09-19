import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getManualSet: vi.fn(),
  getMaterial: vi.fn(),
  insertRows: vi.fn(),
  moveRow: vi.fn(),
  patchRow: vi.fn(),
  removeRow: vi.fn(),
  groupRows: vi.fn(),
  renameBlock: vi.fn(),
  moveBlock: vi.fn(),
  splitBlock: vi.fn(),
  undoSet: vi.fn(),
  redoSet: vi.fn(),
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

const riga = (id: number, blockId: number, position: number) => ({
  id, block_id: blockId, position, slot_kind: "track" as const, track: track(id),
  note: null, alternatives: [],
});

/** Due sequenze nel percorso (una con nome, una senza) e una sul banco. */
const set = (opts: { revision?: number; canUndo?: boolean; canRedo?: boolean } = {}) => ({
  id: 7, name: "Sabato", kind: "manual", revision: opts.revision ?? 1,
  source_playlist_id: 3, source_playlist_name: "Deep", notes: null,
  track_count: 3, total_file_seconds: 900,
  can_undo: opts.canUndo ?? true, can_redo: opts.canRedo ?? false, transitions: [],
  created_at: "2026-09-19T10:00:00", updated_at: "2026-09-19T10:00:00",
  blocks: [
    { id: 1, name: "Apertura", placement: "main" as const, position: 1,
      rows: [riga(10, 1, 1), riga(11, 1, 2)] },
    { id: 2, name: null, placement: "main" as const, position: 2, rows: [riga(12, 2, 1)] },
    { id: 3, name: "Idea", placement: "bench" as const, position: 1, rows: [riga(13, 3, 1)] },
  ],
  reserve: [],
});

const material = () => ({
  playlist_id: 3, playlist_name: "Deep",
  items: [20, 21].map((id) => ({
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

/** La casella di selezione della riga `id`, dentro il pannello del percorso. */
const casella = (id: number) => {
  const li = screen.getByTestId("path-panel").querySelector(`li[data-row="${id}"]`);
  return within(li as HTMLElement).getByLabelText("Seleziona la riga");
};

describe("sequenze", () => {
  it("raggruppa due righe contigue selezionate", async () => {
    api.groupRows.mockResolvedValue(set({ revision: 2 }));
    mount();
    await screen.findByTestId("path-panel");
    fireEvent.click(casella(10));
    fireEvent.click(casella(11));
    fireEvent.click(screen.getByText("Raggruppa"));
    await waitFor(() => expect(api.groupRows).toHaveBeenCalledWith(7, {
      expected_revision: 1, row_ids: [10, 11], name: null,
    }));
  });

  it("senza due righe selezionate «Raggruppa» non c'è", async () => {
    mount();
    await screen.findByTestId("path-panel");
    expect(screen.queryByText("Raggruppa")).toBeNull();
    fireEvent.click(casella(10));
    expect(screen.queryByText("Raggruppa")).toBeNull();
  });

  it("non raggruppa righe di sequenze diverse", async () => {
    // Il rifiuto lo darebbe anche il server, ma il comando non deve nemmeno
    // comparire: un pulsante che risponde con un errore non e' un comando.
    mount();
    await screen.findByTestId("path-panel");
    fireEvent.click(casella(11));
    fireEvent.click(casella(12));
    expect(screen.queryByText("Raggruppa")).toBeNull();
  });

  it("«Sposta sul banco» manda la sequenza al banco, e il banco la rimanda indietro", async () => {
    api.moveBlock.mockResolvedValue(set({ revision: 2 }));
    mount();
    const percorso = within(await screen.findByTestId("path-panel"));
    fireEvent.click(percorso.getAllByTitle("Sposta sul banco")[0]);
    // In coda al banco, che una sequenza ce l'ha già: posizione 2, non 1.
    await waitFor(() => expect(api.moveBlock).toHaveBeenCalledWith(7, 1, {
      expected_revision: 1, position: 2, to_bench: true,
    }));

    // La risposta della prima mossa ha portato il set a revision 2: la seconda
    // manda quella, non piu' la revisione con cui la pagina era nata.
    await waitFor(() => expect(screen.getByTestId("bench-panel")).toBeTruthy());
    api.moveBlock.mockClear();
    const banco = within(screen.getByTestId("bench-panel"));
    fireEvent.click(banco.getByTitle("Rimetti nel percorso"));
    await waitFor(() => expect(api.moveBlock).toHaveBeenCalledWith(7, 3, {
      expected_revision: 2, position: 3, to_bench: false,
    }));
  });

  it("«Separa» scioglie la sequenza", async () => {
    api.splitBlock.mockResolvedValue(set({ revision: 2 }));
    mount();
    const percorso = within(await screen.findByTestId("path-panel"));
    fireEvent.click(percorso.getAllByTitle("Separa la sequenza")[0]);
    await waitFor(() => expect(api.splitBlock).toHaveBeenCalledWith(7, 1, { expected_revision: 1 }));
  });

  it("rinomina una sequenza", async () => {
    api.renameBlock.mockResolvedValue(set({ revision: 2 }));
    mount();
    const percorso = within(await screen.findByTestId("path-panel"));
    fireEvent.click(percorso.getAllByTitle("Rinomina la sequenza")[0]);
    const campo = percorso.getByPlaceholderText("Nome della sequenza");
    fireEvent.change(campo, { target: { value: "Salita" } });
    fireEvent.keyDown(campo, { key: "Enter" });
    await waitFor(() => expect(api.renameBlock).toHaveBeenCalledWith(7, 1, {
      expected_revision: 1, name: "Salita",
    }));
  });

  it("le frecce non attraversano il confine fra due sequenze", async () => {
    // La posizione che il comando manda e' interna alla sequenza: sull'ultima
    // riga di una sequenza «giu'» uscirebbe dall'intervallo valido.
    mount();
    const li = (await screen.findByTestId("path-panel")).querySelector('li[data-row="11"]');
    expect((within(li as HTMLElement).getByTitle("Giù") as HTMLButtonElement).disabled).toBe(true);
    const primo = screen.getByTestId("path-panel").querySelector('li[data-row="12"]');
    expect((within(primo as HTMLElement).getByTitle("Su") as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("annulla e ripeti", () => {
  it("«Annulla» chiama undo con la revisione corrente", async () => {
    api.undoSet.mockResolvedValue(set({ revision: 2, canUndo: false, canRedo: true }));
    mount();
    fireEvent.click(await screen.findByText("Annulla"));
    await waitFor(() => expect(api.undoSet).toHaveBeenCalledWith(7, { expected_revision: 1 }));
  });

  it("senza niente da annullare il pulsante è spento", async () => {
    api.getManualSet.mockResolvedValue(set({ canUndo: false }));
    mount();
    const bottone = await screen.findByText("Annulla");
    expect((bottone.closest("button") as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(bottone);
    expect(api.undoSet).not.toHaveBeenCalled();
  });

  it("«Ripeti» chiama redo", async () => {
    api.getManualSet.mockResolvedValue(set({ canRedo: true }));
    api.redoSet.mockResolvedValue(set({ revision: 2 }));
    mount();
    fireEvent.click(await screen.findByText("Ripeti"));
    await waitFor(() => expect(api.redoSet).toHaveBeenCalledWith(7, { expected_revision: 1 }));
  });

  it("cmd+z annulla", async () => {
    api.undoSet.mockResolvedValue(set({ revision: 2 }));
    mount();
    await screen.findByTestId("path-panel");
    fireEvent.keyDown(window, { key: "z", metaKey: true });
    await waitFor(() => expect(api.undoSet).toHaveBeenCalledWith(7, { expected_revision: 1 }));
  });

  it("cmd+shift+z ripete", async () => {
    api.getManualSet.mockResolvedValue(set({ canRedo: true }));
    api.redoSet.mockResolvedValue(set({ revision: 2 }));
    mount();
    await screen.findByTestId("path-panel");
    fireEvent.keyDown(window, { key: "z", metaKey: true, shiftKey: true });
    await waitFor(() => expect(api.redoSet).toHaveBeenCalledWith(7, { expected_revision: 1 }));
  });

  it("cmd+z dentro l'appunto lo lascia al campo", async () => {
    // Il campo dell'appunto ha il suo annulla nativo: rubarglielo farebbe
    // sparire il set invece della parola appena scritta.
    mount();
    const percorso = within(await screen.findByTestId("path-panel"));
    fireEvent.click(percorso.getByRole("button", { name: /Traccia 10/ }));
    const appunto = await screen.findByPlaceholderText(/Entra sul break/);
    fireEvent.focus(appunto);
    fireEvent.keyDown(appunto, { key: "z", metaKey: true, bubbles: true });
    expect(api.undoSet).not.toHaveBeenCalled();
  });
});
