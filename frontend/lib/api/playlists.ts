import { apiDelete, apiGet, apiPost } from "./client";
import type {
  GapAnalysis,
  LikedTrackPreview,
  Playlist,
  PlaylistDeleteResult,
  PlaylistImportReport,
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

export function deletePlaylist(id: number) {
  return apiDelete<PlaylistDeleteResult>(`/api/playlists/${id}`);
}

export function playlistTracks(id: number, opts?: { signal?: AbortSignal }) {
  return apiGet<Track[]>(`/api/playlists/${id}/tracks`, undefined, opts);
}

/** Avvia in background il riallineamento della playlist con la piattaforma
 *  d'origine (Spotify con prune, SoundCloud solo additivo). */
export function syncPlaylist(id: number) {
  return apiPost<StreamingImportJobStatus>(`/api/playlists/${id}/sync`);
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
