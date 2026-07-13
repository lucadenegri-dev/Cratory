import { apiDelete, apiGet, apiPost } from "./client";
import type { DjSet, DjSetDetail, PlaylistImportReport, ShazamIdentifyState } from "./types";

// --- Shazam: identificazione set DJ (Fase 1) --------------------------------

export function shazamStatus() {
  return apiGet<{ available: boolean }>("/api/shazam/status");
}

export function identifyMix(url: string) {
  return apiPost<ShazamIdentifyState>("/api/shazam/identify", { url });
}

export function shazamIdentifyStatus() {
  return apiGet<ShazamIdentifyState>("/api/shazam/identify-status");
}

export function listDjSets() {
  return apiGet<DjSet[]>("/api/shazam/sets");
}

export function getDjSet(id: number) {
  return apiGet<DjSetDetail>(`/api/shazam/sets/${id}`);
}

/** Promuove le tracce identificate del set a lead in una playlist 'manual'. */
export function importDjSetAsPlaylist(id: number) {
  return apiPost<PlaylistImportReport>(`/api/shazam/sets/${id}/import-playlist`);
}

export function deleteDjSet(id: number) {
  return apiDelete<void>(`/api/shazam/sets/${id}`);
}
