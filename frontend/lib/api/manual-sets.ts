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

export function getMaterial(id: number, opts: { q?: string; owned?: boolean; unused?: boolean } = {}) {
  const p = new URLSearchParams();
  if (opts.q) p.set("q", opts.q);
  if (opts.owned) p.set("owned", "true");
  if (opts.unused) p.set("unused", "true");
  const qs = p.toString();
  return apiGet<Material>(`/api/sets/${id}/material${qs ? `?${qs}` : ""}`);
}

export function insertRows(
  id: number,
  body: { expected_revision: number; track_ids?: number[]; gap?: boolean; after_row_id?: number | null },
) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows`, body);
}

export function moveRow(id: number, rowId: number, body: { expected_revision: number; position: number }) {
  return apiPost<ManualSet>(`/api/sets/${id}/rows/${rowId}/move`, body);
}

export function patchRow(id: number, rowId: number, body: { expected_revision: number; note: string | null }) {
  return apiPatch<ManualSet>(`/api/sets/${id}/rows/${rowId}`, body);
}

export function removeRow(id: number, rowId: number, expectedRevision: number) {
  return apiDelete<ManualSet>(`/api/sets/${id}/rows/${rowId}?expected_revision=${expectedRevision}`);
}
