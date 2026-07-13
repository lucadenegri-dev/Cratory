import { apiGet, apiPost, apiPut, apiUpload } from "./client";
import type {
  LabelStats,
  PipelineStatus,
  RekordboxImportReport,
  ServiceStatus,
  SoundCloudLikedTrackPreview,
  SoundCloudStatus,
  StreamingImportJobStatus,
} from "./types";

export function getPipeline() {
  return apiGet<PipelineStatus>("/api/pipeline");
}

// --- SoundCloud ---------------------------------------------------------------

export function soundcloudStatus() {
  return apiGet<SoundCloudStatus>("/api/soundcloud/status");
}

export function setSoundcloudUsername(username: string) {
  return apiPut<SoundCloudStatus>("/api/soundcloud/config", { username });
}

/** Avvia in background l'import di una playlist SoundCloud da URL (pubblica o
 *  secret link). Solo metadati. */
export function importSoundcloudPlaylist(url: string) {
  return apiPost<StreamingImportJobStatus>("/api/soundcloud/import", { url });
}

/** Anteprima di TUTTI i like SoundCloud: non importa nulla (nessun cap). */
export function previewSoundcloudLikes() {
  return apiGet<SoundCloudLikedTrackPreview[]>("/api/soundcloud/likes/preview");
}

/** Avvia in background l'import nella playlist "SoundCloud Likes" dei soli
 *  brani selezionati (additivo). */
export function importSelectedSoundcloudLikes(trackIds: string[]) {
  return apiPost<StreamingImportJobStatus>("/api/soundcloud/import/likes", { track_ids: trackIds });
}

export function getLabels() {
  return apiGet<LabelStats[]>("/api/labels");
}

export function servicesStatus() {
  return apiGet<{ services: ServiceStatus[] }>("/api/services/status");
}

// --- Rekordbox (import collezione XML) --------------------------------------

export async function importRekordbox(file: File, overwrite = false) {
  const fd = new FormData();
  fd.append("file", file);
  return apiUpload<RekordboxImportReport>(
    `/api/rekordbox/import${overwrite ? "?overwrite=true" : ""}`, fd,
  );
}
