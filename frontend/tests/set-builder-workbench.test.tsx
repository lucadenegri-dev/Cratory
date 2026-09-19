import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  getManualSet: vi.fn(),
  getMaterial: vi.fn(),
  insertRows: vi.fn(),
  moveRow: vi.fn(),
  patchRow: vi.fn(),
  removeRow: vi.fn(),
  apiDelete: vi.fn(),
  renameSet: vi.fn(),
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
import { ApiError } from "@/lib/api";
import { PlayerProvider } from "@/lib/player";

// TrackPlayButton usa usePlayer(): la pagina va montata dentro il provider.
const mount = () => render(<PlayerProvider><ManualSetPage /></PlayerProvider>);

const track = (id: number, extra = {}) => ({
  id, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
  title: `Traccia ${id}`, artist: "Artista", album: null, genre: null, year: null,
  duration_seconds: 300, bpm: id === 2 ? null : 124, camelot_key: id === 2 ? null : "8A", energy: null,
  label: null, status: "imported", url: null, isrc: null, playlists: [], added_at: null,
  spotify_url: null, album_art_url: null, has_local_file: true, rating: null, ...extra,
});

const set = (revision = 0, rows: Array<{ id: number; track: ReturnType<typeof track> | null }> = []) => ({
  id: 7, name: "Sabato", kind: "manual", revision, sources: [{ playlist_id: 3, name: "Deep" }],
  notes: null, track_count: rows.filter((r) => r.track).length, total_file_seconds: 300 * rows.filter((r) => r.track).length,
  can_undo: false, can_redo: false, transitions: [],
  duration: { seconds: 0, incomplete: false, unknown_rows: 0, open_gaps: 0 },
  created_at: "2026-09-17T10:00:00", updated_at: "2026-09-17T10:00:00",
  blocks: rows.length ? [{ id: 1, name: null, placement: "main" as const, position: 1,
    rows: rows.map((r, i) => ({ id: r.id, block_id: 1, position: i + 1, slot_kind: r.track ? "track" as const : "gap" as const, track: r.track, note: null, alternatives: [] })) }] : [],
  reserve: [],
});

const material = (inSet: number[] = []) => ({
  sources: [{ playlist_id: 3, name: "Deep" }],
  items: [1, 2].map((id) => ({ track: track(id), in_set: inSet.includes(id), from_playlist: true, in_reserve: false })),
});

beforeEach(() => {
  api.getManualSet.mockResolvedValue(set());
  api.getMaterial.mockResolvedValue(material());
  api.apiDelete.mockResolvedValue(undefined);
});
afterEach(() => {
  cleanup();
  Object.values(api).forEach((f) => f.mockReset());
  push.mockReset();
});

describe("set manuale: il gesto base", () => {
  it("mostra materiale e percorso vuoto", async () => {
    mount();
    // I titoli sono "Artista – Traccia 1": nodi di testo separati, si cerca con la regex.
    expect(await screen.findByText(/Traccia 1/)).toBeTruthy();
    expect(screen.getByText(/Aggiungi tracce dal materiale/)).toBeTruthy();
    // La provenienza non sta piu' in intestazione: dal 2026-09-19 le origini
    // sono piu' d'una e vivono nel pannello del materiale, dove si cambiano.
    expect(within(screen.getByTestId("sources-panel")).getByText("Deep")).toBeTruthy();
  });

  it("aggiunge una traccia con la revisione corrente e ricarica il materiale", async () => {
    api.insertRows.mockResolvedValue(set(1, [{ id: 10, track: track(1) }]));
    api.getMaterial.mockResolvedValueOnce(material()).mockResolvedValueOnce(material([1]));
    mount();
    await screen.findByText(/Traccia 1/);
    fireEvent.click(screen.getAllByTitle("Aggiungi al percorso")[0]);
    await waitFor(() => expect(api.insertRows).toHaveBeenCalledWith(7, { expected_revision: 0, track_ids: [1], after_row_id: null }));
    await waitFor(() => expect(api.getMaterial).toHaveBeenCalledTimes(2));
    expect(screen.getAllByText("nel set").length).toBeGreaterThan(0);
  });

  it("mostra 'sconosciuto' sui dati mancanti, e la durata quando c'e'", async () => {
    api.getManualSet.mockResolvedValue(set(1, [{ id: 10, track: track(2) }]));
    mount();
    // La riga del percorso e' un <button>; nel materiale la stessa traccia non lo e'.
    const inPath = (await screen.findAllByText(/Traccia 2/)).find((el) => el.closest("button"));
    fireEvent.click(inPath!);
    const detail = within(screen.getByTestId("detail-panel"));
    // Tre celle su quattro sono vuote nel fixture (bpm, camelot, genere): il
    // denominatore conta, perche' con un numero piu' alto il test passerebbe
    // anche se una cella smettesse di comparire del tutto.
    expect((await detail.findAllByText("sconosciuto")).length).toBe(3);
    // La quarta ha un valore, e non dice "sconosciuto" ma il tempo formattato.
    expect(detail.getByText("Genere")).toBeTruthy();
    expect(detail.getByText("Durata")).toBeTruthy();
    expect(detail.getByText("5:00")).toBeTruthy();
  });

  it("su una traccia non c'e' l'appunto di riga: lo dicono i passaggi", async () => {
    // Dal 2026-09-19 «Il tuo appunto» resta solo sui varchi (vedi il test dopo).
    api.getManualSet.mockResolvedValue(set(1, [{ id: 10, track: track(2) }]));
    mount();
    const inPath = (await screen.findAllByText(/Traccia 2/)).find((el) => el.closest("button"));
    fireEvent.click(inPath!);
    await screen.findByTestId("detail-panel");
    expect(screen.queryByPlaceholderText(/Entra sul break/)).toBeNull();
  });

  it("salva l'appunto del varco al blur", async () => {
    // Un varco non produce passaggi: questo campo e' l'unico posto in cui
    // scriverci sopra, ed e' cio' che l'export stampa accanto al varco.
    api.getManualSet.mockResolvedValue(set(1, [{ id: 10, track: null }]));
    api.patchRow.mockResolvedValue(set(2, [{ id: 10, track: null }]));
    mount();
    const percorso = within(await screen.findByTestId("path-panel"));
    fireEvent.click(percorso.getByRole("button", { name: /Varco/ }));
    const area = await screen.findByPlaceholderText(/Entra sul break/);
    fireEvent.change(area, { target: { value: "apre bene" } });
    fireEvent.blur(area);
    await waitFor(() => expect(api.patchRow).toHaveBeenCalledWith(7, 10, { expected_revision: 1, note: "apre bene" }));
    expect(await screen.findByText("Salvato")).toBeTruthy();
  });

  it("su 409 mostra il conflitto e Ricarica rilegge il set", async () => {
    api.getManualSet.mockResolvedValue(set(0));
    api.insertRows.mockRejectedValue(new ApiError("cambiato", 409, "set_revision_conflict"));
    mount();
    await screen.findByText(/Traccia 1/);
    fireEvent.click(screen.getAllByTitle("Aggiungi al percorso")[0]);
    expect(await screen.findByText("Il set è cambiato altrove")).toBeTruthy();
    fireEvent.click(screen.getByText("Ricarica"));
    await waitFor(() => expect(api.getManualSet).toHaveBeenCalledTimes(2));
  });
});

describe("set manuale: rinomina", () => {
  it("manda il nome ripulito dagli spazi", async () => {
    api.renameSet.mockResolvedValue({ id: 7, name: "Domenica" });
    mount();
    await screen.findByText("Sabato");
    fireEvent.click(screen.getByRole("button", { name: /Rinomina/ }));
    const campo = await screen.findByLabelText("Nome del set");
    fireEvent.change(campo, { target: { value: "  Domenica  " } });
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    await waitFor(() => expect(api.renameSet).toHaveBeenCalledWith(7, "Domenica"));
  });

  it("l'intestazione mostra il nome salvato dal server, non quello digitato", async () => {
    // Il nome salvato lo decide il backend (lo taglia ai bordi, lo tronca a
    // 200). Qui la risposta differisce apposta da cio' che si e' scritto: e'
    // l'unico modo di distinguere «mostro la risposta» da «mostro la mia
    // ipotesi» — con lo stesso testo i due casi sarebbero indistinguibili.
    api.renameSet.mockResolvedValue({ id: 7, name: "Domenica sera" });
    mount();
    await screen.findByText("Sabato");
    fireEvent.click(screen.getByRole("button", { name: /Rinomina/ }));
    const campo = await screen.findByLabelText("Nome del set");
    fireEvent.change(campo, { target: { value: "Domenica" } });
    fireEvent.click(screen.getByRole("button", { name: "Salva" }));
    expect(await screen.findByText("Domenica sera")).toBeTruthy();
    expect(screen.queryByText("Sabato")).toBeNull();
  });

  it("un nome vuoto non parte", async () => {
    mount();
    await screen.findByText("Sabato");
    fireEvent.click(screen.getByRole("button", { name: /Rinomina/ }));
    const campo = await screen.findByLabelText("Nome del set");
    fireEvent.change(campo, { target: { value: "   " } });
    fireEvent.keyDown(campo, { key: "Enter" });
    expect(api.renameSet).not.toHaveBeenCalled();
    // E il modal resta aperto: chiuderlo fingerebbe che sia andata bene.
    expect(screen.getByLabelText("Nome del set")).toBeTruthy();
  });
});

describe("set manuale: eliminazione", () => {
  it("chiede conferma prima di eliminare", async () => {
    mount();
    await screen.findByText(/Traccia 1/);
    expect(screen.queryByText("Eliminare il set?")).toBeNull();
    fireEvent.click(screen.getByText("Elimina set"));
    expect(await screen.findByText("Eliminare il set?")).toBeTruthy();
    expect(screen.getByText("«Sabato» verrà eliminato definitivamente.")).toBeTruthy();
    expect(api.apiDelete).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });

  it("confermando chiama l'endpoint di cancellazione e torna a /sets", async () => {
    mount();
    await screen.findByText(/Traccia 1/);
    fireEvent.click(screen.getByText("Elimina set"));
    await screen.findByText("Eliminare il set?");
    // Due bottoni "Elimina...": quello nel footer del modal e' "Elimina" (common.delete).
    fireEvent.click(screen.getByRole("button", { name: "Elimina" }));
    await waitFor(() => expect(api.apiDelete).toHaveBeenCalledWith("/api/sets/7"));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/sets"));
  });

  it("annullando non chiama l'endpoint ne' naviga", async () => {
    mount();
    await screen.findByText(/Traccia 1/);
    fireEvent.click(screen.getByText("Elimina set"));
    await screen.findByText("Eliminare il set?");
    // «Annulla» e' anche il comando di cronologia in cima alla pagina: qui
    // serve quello del modal, non quello che tornerebbe indietro di un gesto.
    fireEvent.click(within(screen.getByRole("dialog")).getByText("Annulla"));
    await waitFor(() => expect(screen.queryByText("Eliminare il set?")).toBeNull());
    expect(api.apiDelete).not.toHaveBeenCalled();
    expect(push).not.toHaveBeenCalled();
  });
});
