import { API, apiGet, apiPatch, apiPost } from "./client";
import type { LibraryIndexJob, TrackDetail, TrackUpdate } from "./types";

/** Modifica manuale di una traccia: i valori inseriti hanno la precedenza sull'enrichment. */
export function updateTrack(id: number, patch: TrackUpdate) {
  return apiPatch<TrackDetail>(`/api/tracks/${id}`, patch);
}

/** Indicizza la libreria canonica (LIBRARY_ROOT): il disco è la libreria. */
export function startLibraryIndex() {
  return apiPost<LibraryIndexJob>("/api/library/index");
}

export function libraryIndexStatus() {
  return apiGet<LibraryIndexJob>("/api/library/index/status");
}

/** Sorgente cover di una traccia: Spotify se presente, altrimenti l'artwork
 *  embedded nel file (endpoint on-demand) per le possedute, altrimenti nessuna. */
export function trackCoverSrc(
  t: { id: number; album_art_url?: string | null; has_local_file?: boolean | null },
): string | null {
  if (t.album_art_url) return t.album_art_url;
  if (t.has_local_file) return `${API}/api/tracks/${t.id}/cover`;
  return null;
}
