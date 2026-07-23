import { apiDelete, apiGet, apiPost } from "./client";
import type {
  AutoLinkProposal,
  DownloadCandidate,
  DownloadReview,
  DownloadStatus,
  LocalFileHit,
  Track,
} from "./types";

export function downloadTrackAuto(trackId: number) {
  return apiPost<DownloadStatus>("/api/downloads/track/auto", { track_id: trackId });
}

export function downloadTrackSoundcloud(trackId: number) {
  return apiPost<DownloadStatus>("/api/downloads/track/soundcloud", { track_id: trackId });
}

// --- Download (Soulseek/slskd) ----------------------------------------------

export function downloadStatus() {
  return apiGet<DownloadStatus>("/api/downloads/status");
}

export function downloadCandidates(artist: string, title: string, durationSeconds?: number | null) {
  // La durata attesa (se nota) premia nel ranking la versione giusta.
  return apiPost<DownloadCandidate[]>("/api/downloads/candidates",
    { artist, title, duration_seconds: durationSeconds ?? undefined });
}

export function startPlaylistDownload(playlistId: number) {
  return apiPost<DownloadStatus>(`/api/downloads/playlist/${playlistId}`);
}

export function downloadPending(opts?: { signal?: AbortSignal }) {
  return apiGet<Track[]>("/api/downloads/pending", undefined, opts);
}

export function retryPending() {
  return apiPost<DownloadStatus>("/api/downloads/retry-pending");
}

export function downloadTrack(trackId: number, candidate: DownloadCandidate) {
  return apiPost<DownloadStatus>("/api/downloads/track", { track_id: trackId, candidate });
}

export function searchDownloads(query: string) {
  return apiPost<DownloadCandidate[]>("/api/downloads/search", { query });
}

export function downloadManual(candidate: DownloadCandidate) {
  return apiPost<DownloadStatus>("/api/downloads/manual", { candidate });
}

/** "Ignora": azzera l'esito download, la traccia esce dall'archivio da sistemare. */
export function ignoreDownload(trackId: number) {
  return apiDelete<Track>(`/api/downloads/pending/${trackId}`);
}

// --- File locali (collegamento manuale) ---------------------------------------

/** Cerca file audio per nome in LIBRARY_ROOT e nella cartella download slskd. */
export function searchLocalFiles(q: string) {
  return apiGet<LocalFileHit[]>("/api/files/search", { q });
}

/** Collega manualmente un file su disco alla traccia (possesso senza download). */
export function linkLocalFile(trackId: number, path: string) {
  return apiPost<Track>(`/api/tracks/${trackId}/link-file`, { path });
}

// --- Revisione file dubbio (needs_review-per-durata) --------------------------

/** Atteso vs file già scaricato per una traccia da rivedere. */
export function downloadReview(trackId: number) {
  return apiGet<DownloadReview>(`/api/downloads/review/${trackId}`);
}

/** Tieni il file dubbio: lo aggancia come possesso e svuota l'esito. */
export function keepReview(trackId: number) {
  return apiPost<Track>("/api/downloads/keep-review", { track_id: trackId });
}

/** Scarta il file dubbio: lo elimina dall'inbox e sgancia la traccia. */
export function discardReview(trackId: number) {
  return apiPost<Track>("/api/downloads/discard-review", { track_id: trackId });
}

// --- Auto-collega file locale su tutte le da sistemare ------------------------

/** Per ogni traccia da sistemare, il miglior file locale che combacia (o null). Non collega. */
export function autoLinkPreview() {
  return apiGet<AutoLinkProposal[]>("/api/downloads/auto-link");
}
