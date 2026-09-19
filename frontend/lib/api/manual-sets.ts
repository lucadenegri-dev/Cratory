import { apiDelete, apiGet, apiPatch, apiPost } from "./client";
import type { ManualSet, Material } from "./types";

/** Set preparato a mano (tappa 1): tutte le mutazioni mandano `expected_revision`;
 *  un 409 `set_revision_conflict` vuol dire "ricarica e riprova". */
export function createManualSet(body: { name?: string; playlist_id?: number | null }) {
  return apiPost<ManualSet>("/api/sets/manual", body);
}

export function getManualSet(id: number) {
  return apiGet<ManualSet>(`/api/sets/${id}/manual`);
}

export function getMaterial(
  id: number,
  opts: { q?: string; owned?: boolean; unused?: boolean; reserved?: boolean } = {},
) {
  const p = new URLSearchParams();
  if (opts.q) p.set("q", opts.q);
  if (opts.owned) p.set("owned", "true");
  if (opts.unused) p.set("unused", "true");
  if (opts.reserved) p.set("reserved", "true");
  const qs = p.toString();
  return apiGet<Material>(`/api/sets/${id}/material${qs ? `?${qs}` : ""}`);
}

export function insertRows(
  id: number,
  body: { expected_revision: number; track_ids?: number[]; gap?: boolean; after_row_id?: number | null; reserve?: boolean },
) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows`, body);
}

export function moveRow(
  id: number,
  rowId: number,
  body: { expected_revision: number; position: number; to_reserve?: boolean | null },
) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows/${rowId}/move`, body);
}

export function patchRow(id: number, rowId: number, body: { expected_revision: number; note: string | null }) {
  return apiPatch<ManualSet>(`/api/sets/${id}/rows/${rowId}`, body);
}

export function removeRow(id: number, rowId: number, expectedRevision: number) {
  return apiDelete<ManualSet>(`/api/sets/${id}/rows/${rowId}?expected_revision=${expectedRevision}`);
}

/** Candidate tenute dal DJ su una riga: non sono le alternative calcolate dal
 *  vecchio generatore, che vivono su un altro endpoint e su altri set. */
export function addAlternatives(id: number, rowId: number, body: { expected_revision: number; track_ids: number[] }) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows/${rowId}/alternatives`, body);
}

export function removeAlternative(id: number, rowId: number, altId: number, expectedRevision: number) {
  return apiDelete<ManualSet>(`/api/sets/${id}/rows/${rowId}/alternatives/${altId}?expected_revision=${expectedRevision}`);
}

/** Scambio: la candidata diventa attiva e la traccia uscente resta fra le candidate. */
export function chooseAlternative(id: number, rowId: number, altId: number, body: { expected_revision: number }) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows/${rowId}/alternatives/${altId}/choose`, body);
}

/** Sequenze (tappa 3): i blocchi `main` del percorso e quelli `bench` del banco.
 *  Le righe restano dove sono, cambia solo come sono divise. */
export function groupRows(
  id: number,
  body: { expected_revision: number; row_ids: number[]; name?: string | null },
) {
  return apiPost<ManualSet>(`/api/sets/${id}/blocks`, body);
}

export function renameBlock(id: number, blockId: number, body: { expected_revision: number; name: string | null }) {
  return apiPatch<ManualSet>(`/api/sets/${id}/blocks/${blockId}`, body);
}

export function moveBlock(
  id: number,
  blockId: number,
  body: { expected_revision: number; position: number; to_bench?: boolean | null },
) {
  return apiPost<ManualSet>(`/api/sets/${id}/blocks/${blockId}/move`, body);
}

export function splitBlock(id: number, blockId: number, body: { expected_revision: number }) {
  return apiPost<ManualSet>(`/api/sets/${id}/blocks/${blockId}/split`, body);
}

/** Annulla e ripeti. Attenzione: `revision` cresce anche annullando, quindi la
 *  risposta e' sempre la verita' da rimettere nello stato. */
export function undoSet(id: number, body: { expected_revision: number }) {
  return apiPost<ManualSet>(`/api/sets/${id}/undo`, body);
}

export function redoSet(id: number, body: { expected_revision: number }) {
  return apiPost<ManualSet>(`/api/sets/${id}/redo`, body);
}
