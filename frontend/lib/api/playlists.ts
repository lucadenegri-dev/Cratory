import { API, apiDelete, apiGet, apiPatch, apiPost, apiPut } from "./client";
import type {
  GapAnalysis,
  LikedTrackPreview,
  Playlist,
  PlaylistAddTracksResult,
  PlaylistDeleteResult,
  PlaylistImportReport,
  PlaylistSyncEvent,
  SpotifyPlaylistRef,
  StreamingImportJobStatus,
  Track,
} from "./types";

// --- Playlist (nuovo flusso) ------------------------------------------------

export function listSpotifyPlaylists() {
  return apiGet<SpotifyPlaylistRef[]>("/api/playlists/spotify/available");
}

export function streamingImportStatus() {
  return apiGet<StreamingImportJobStatus>("/api/playlists/import/status");
}

/** Avvia in background l'import di una playlist (o dei liked) da Spotify. */
export function importPlaylist(playlistId: string) {
  return apiPost<StreamingImportJobStatus>("/api/playlists/import", {
    platform: "spotify",
    playlist_id: playlistId,
  });
}

/** Anteprima dei liked Spotify: non importa nulla, marca i già presenti in libreria. */
export function previewLikedTracks() {
  return apiGet<LikedTrackPreview[]>("/api/playlists/spotify/liked/preview");
}

/** Avvia in background l'import nella playlist "Spotify Likes" dei soli brani
 *  selezionati (additivo). */
export function importSelectedLikedTracks(spotifyIds: string[]) {
  return apiPost<StreamingImportJobStatus>("/api/playlists/import/liked/selected", {
    spotify_ids: spotifyIds,
  });
}

export function listImportedPlaylists() {
  return apiGet<Playlist[]>("/api/playlists");
}

export function getPlaylist(id: number, opts?: { signal?: AbortSignal }) {
  return apiGet<Playlist>(`/api/playlists/${id}`, undefined, opts);
}

/** Rinomina la playlist. Il nome scelto e' definitivo: il sync non lo sovrascrive. */
export function renamePlaylist(id: number, name: string) {
  return apiPatch<Playlist>(`/api/playlists/${id}`, { name });
}

export function deletePlaylist(id: number) {
  return apiDelete<PlaylistDeleteResult>(`/api/playlists/${id}`);
}

export function playlistTracks(id: number, opts?: { signal?: AbortSignal }) {
  return apiGet<Track[]>(`/api/playlists/${id}/tracks`, undefined, opts);
}

/** Toglie una singola traccia dalla playlist. Se diventa un lead orfano viene
 *  rimossa: `deleted_tracks` = 1 in quel caso, 0 se resta in libreria. */
export function removeTrackFromPlaylist(playlistId: number, trackId: number) {
  return apiDelete<PlaylistDeleteResult>(`/api/playlists/${playlistId}/tracks/${trackId}`);
}

/** Fork della playlist in una copia manuale (riordinabile/editabile). */
export function duplicatePlaylist(id: number, name?: string) {
  return apiPost<Playlist>(`/api/playlists/${id}/duplicate`, { name: name ?? null });
}

/** Toglie più tracce dalla playlist (bulk); i lead orfani vengono cancellati. */
export function removeTracksFromPlaylist(playlistId: number, trackIds: number[]) {
  return apiPost<{ removed: number; deleted_tracks: number }>(
    `/api/playlists/${playlistId}/tracks/remove`, { track_ids: trackIds });
}

export type PlaylistExportFormat = "m3u8" | "csv" | "text" | "markdown";

/** Export della playlist nel formato scelto (default M3U8 per Rekordbox). */
export async function exportPlaylist(id: number, format: PlaylistExportFormat = "m3u8"): Promise<string> {
  const res = await fetch(`${API}/api/playlists/${id}/export?format=${format}`, { method: "POST" });
  if (!res.ok) throw new Error(res.statusText);
  return res.text();
}

/** Avvia in background il riallineamento della playlist con la piattaforma
 *  d'origine (Spotify con prune, SoundCloud solo additivo). */
export function syncPlaylist(id: number) {
  return apiPost<StreamingImportJobStatus>(`/api/playlists/${id}/sync`);
}

/** Avvia in background il riallineamento di tutte le playlist Spotify e
 *  SoundCloud importate (liked esclusi). */
export function syncAllPlaylists() {
  return apiPost<StreamingImportJobStatus>("/api/playlists/sync-all");
}

/** Ultimi diff di import/sync della playlist (più recente prima). */
export function playlistSyncLog(id: number, opts?: { signal?: AbortSignal }) {
  return apiGet<PlaylistSyncEvent[]>(`/api/playlists/${id}/sync-log`, undefined, opts);
}

export function playlistGaps(id: number, opts?: { signal?: AbortSignal }) {
  return apiGet<GapAnalysis>(`/api/playlists/${id}/gaps`, undefined, opts);
}

export function libraryGaps() {
  return apiGet<GapAnalysis>("/api/playlists/library/gaps");
}

export function createPlaylistFromTracks(name: string, trackIds: number[]) {
  return apiPost<Playlist>("/api/playlists/create-from-tracks", { name, track_ids: trackIds });
}

export function importManualPlaylist(name: string, text: string) {
  return apiPost<PlaylistImportReport>("/api/playlists/import-manual", { name, text });
}

/** Aggiunge tracce a una playlist esistente (idempotente, additivo).
 *  `added` = nuove membership create, `skipped` = tracce gia' presenti. */
export function addTracksToPlaylist(playlistId: number, trackIds: number[]) {
  return apiPost<PlaylistAddTracksResult>(`/api/playlists/${playlistId}/add-tracks`, {
    track_ids: trackIds,
  });
}

/** Sposta una traccia alla posizione 1-based indicata (solo playlist manuali).
 *  Ritorna la lista tracce riordinata. */
export function reorderPlaylistTrack(playlistId: number, trackId: number, position: number) {
  return apiPost<Track[]>(`/api/playlists/${playlistId}/reorder`, { track_id: trackId, position });
}

/** Sostituisce l'ordine completo della playlist (drag-and-drop): permutazione
 *  esatta dei membri. Ritorna la lista riordinata. */
export function setPlaylistOrder(playlistId: number, trackIds: number[]) {
  return apiPut<Track[]>(`/api/playlists/${playlistId}/order`, { track_ids: trackIds });
}
