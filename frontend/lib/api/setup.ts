import { apiGet, apiPost, apiPut } from "./client";

/** Stato di una credenziale: il valore non arriva mai dal backend. */
export type SecretState = {
  configured: boolean;
  source: "env" | "db";
  hint: string | null;
};

export type SecretKey =
  | "spotify_client_id" | "spotify_client_secret" | "ai_api_key"
  | "discogs_token" | "acoustid_api_key" | "slskd_api_key";

export type ProbeComponent = {
  key: string;
  kind: "system" | "daemon";
  severity: "required" | "optional";
  present: boolean;
  version: string | null;
  source: "bundle" | "path" | "override" | "daemon" | null;
  /** Path to a system copy of the binary that this component's version is shadowing,
   *  or null if there is no system copy or this component is not in use. */
  shadowing: string | null;
  auto_installable: boolean;
  /** Esiste una build nel manifesto per questa piattaforma: se è false, il
   *  bottone Installa non ha senso e si mostra il comando manuale. */
  installable: boolean;
  install_command: string[] | null;
  unlocks: string[];
  /** Dove leggere se la ricetta non fa al caso proprio (o non esiste). */
  docs: string;
};

export type ProbeResponse = { platform: string; components: ProbeComponent[] };

export type InstallStatus = {
  key: string | null;
  status: "idle" | "running" | "done" | "error";
  log: string[];
  detail: string | null;
  /** "checksum_mismatch" | "unsafe_archive" | null/assente: le due sole
   *  eccezioni che meritano un messaggio d'allarme invece del generico
   *  "installazione fallita" — vedi component-row.tsx. Opzionale (non
   *  `| undefined` esplicito ma non richiesto) solo per non forzare ogni
   *  fixture di test a portarlo: il backend lo manda sempre. */
  error_code?: string | null;
};

export type CredentialTestResult = { ok: boolean; code: string; detail: string };

export type SetupState = { completed: boolean };

/** Il wizard è già stato completato o saltato? */
export function getSetupState() {
  return apiGet<SetupState>("/api/setup/state");
}

/** Segna il wizard come completato (o lo riapre). */
export function setSetupCompleted(completed: boolean) {
  return apiPut<SetupState>("/api/setup/state", { completed });
}

/** Stato dei componenti esterni. `force` bypassa la cache del backend. */
export function getProbe(force = false) {
  return apiGet<ProbeResponse>("/api/setup/probe", force ? { force: true } : undefined);
}

/** Avvia l'installazione di un componente auto-installabile. */
export function startInstall(key: string) {
  return apiPost<InstallStatus>(`/api/setup/install/${key}`);
}

export function getInstallStatus() {
  return apiGet<InstallStatus>("/api/setup/install/status");
}

/** Prova reale della credenziale presso il provider. */
export function testCredential(service: string) {
  return apiPost<CredentialTestResult>(`/api/setup/test/${service}`);
}
