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
  kind: "system" | "venv" | "daemon";
  severity: "required" | "optional";
  present: boolean;
  version: string | null;
  source: "bundle" | "path" | "venv" | "daemon" | null;
  auto_installable: boolean;
  install_command: string[] | null;
  unlocks: string[];
};

export type ProbeResponse = { platform: string; components: ProbeComponent[] };

export type InstallStatus = {
  key: string | null;
  status: "idle" | "running" | "done" | "error";
  log: string[];
  detail: string | null;
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
