import { apiGet } from "./client";

export type UpdateCheckResult = {
  current: string;
  latest: string | null;
  update_available: boolean;
  url: string | null;
  /** Note scritte su GitHub: contenuto di terzi, non testo dell'app. */
  notes: string | null;
  /** Peso dell'artefatto che l'updater scarica, in byte. `null` quando non si
   *  sa: chi lo mostra deve tacerlo, non stimarlo. */
  size_bytes: number | null;
};

/** La versione in esecuzione. */
export function getAppVersion() {
  return apiGet<{ version: string }>("/api/version");
}

/** Esiste una versione più recente? Solleva se non è stato possibile
 *  stabilirlo — "non lo so" non deve somigliare a "sei aggiornato". */
export function checkUpdates() {
  return apiGet<UpdateCheckResult>("/api/updates/check");
}
