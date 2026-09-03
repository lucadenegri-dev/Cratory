import { apiGet, apiPost, apiPut } from "./client";
import type { SlskdStatus } from "./types";

/** Stato del login alla rete Soulseek (via demone slskd). */
export function slskdStatus() {
  return apiGet<SlskdStatus>("/api/slskd/status");
}

/** Connette il demone alla rete Soulseek (login con le credenziali gia' in slskd). */
export function slskdConnect() {
  return apiPost<SlskdStatus>("/api/slskd/connect");
}

/** Disconnette il demone dalla rete Soulseek. */
export function slskdDisconnect() {
  return apiPost<SlskdStatus>("/api/slskd/disconnect");
}

export type SlskdDaemonStatus = {
  reachable: boolean;
  owned: boolean | null;
  pid: number | null;
  /** Il binario è nella cartella gestita dall'app. */
  installed: boolean;
  /** Il file YAML di slskd esiste. */
  configured: boolean;
  /** L'account Soulseek letto dal file: si mostra senza richiederlo. La
   *  password non torna mai indietro dal backend. */
  username: string | null;
};

/** Stato del demone: raggiungibile via HTTP, e se l'abbiamo avviato noi. */
export function daemonStatus() {
  return apiGet<SlskdDaemonStatus>("/api/slskd/daemon/status");
}

/** Avvia il demone. 409 se è già acceso o se il binario non c'è, 502 se non risponde. */
export function daemonStart() {
  return apiPost<SlskdDaemonStatus>("/api/slskd/daemon/start");
}

/** Ferma il demone — solo se l'abbiamo avviato noi (409 altrimenti). */
export function daemonStop() {
  return apiPost<SlskdDaemonStatus>("/api/slskd/daemon/stop");
}

export type ApiKeyRepair = {
  /** La chiave c'e', nel file di slskd e nelle impostazioni di Cratory. */
  configured: boolean;
  /** L'abbiamo riavviato noi (solo se il demone e' nostro). */
  restarted: boolean;
  /** ...altrimenti tocca all'utente: slskd legge le api_keys solo all'avvio. */
  needs_restart: boolean;
};

/** Ripara l'autenticazione: scrive la chiave API in slskd.yml, la specchia
 *  nelle impostazioni e riavvia il demone se e' nostro. 409 se slskd non e'
 *  ancora configurato. */
export function repairApiKey() {
  return apiPost<ApiKeyRepair>("/api/slskd/daemon/api-key");
}

/** Scrive le credenziali Soulseek nel slskd.yml. La password non torna indietro. */
export function daemonConfig(body: {
  username: string; password: string; port?: number; download_dir?: string;
}) {
  return apiPut<{ configured: boolean; username: string }>("/api/slskd/daemon/config", body);
}
