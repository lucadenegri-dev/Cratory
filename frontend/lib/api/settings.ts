import { apiGet, apiPatch, apiPost, apiPut } from "./client";
import type { ConfigPatch, ConfigSettings, ShareLibraryResult } from "./types";

/** Config editabile (path/URL) con override runtime sui default di backend/.env. */
export function getConfigSettings() {
  return apiGet<ConfigSettings>("/api/settings/config");
}

/** Aggiorna gli override. Campo assente = invariato; stringa vuota = azzera (torna a .env). */
export function patchConfigSettings(patch: ConfigPatch) {
  return apiPatch<ConfigSettings>("/api/settings/config", patch);
}

/** Attiva/disattiva la condivisione della libreria su Soulseek (edita slskd.yml). */
export function setLibraryShare(enabled: boolean) {
  return apiPut<ShareLibraryResult>("/api/settings/share-library", { enabled });
}

/** Quanti download Soulseek in parallelo (1-10, il backend risponde 422 fuori scala). */
export function setDownloadSlots(slots: number) {
  return apiPut<{ download_slots: number }>("/api/settings/download-slots", { slots });
}

/** Il dialog nativo di scelta percorso è disponibile? (solo backend su macOS) */
export function pickerAvailability() {
  return apiGet<{ available: boolean }>("/api/files/pick/availability");
}

/** Apre il dialog nativo sulla macchina del backend; path null = annullato. */
export function pickPath(kind: "folder" | "file", start?: string, prompt?: string) {
  return apiPost<{ path: string | null }>("/api/files/pick", {
    kind, start: start || null, prompt: prompt || null,
  });
}
