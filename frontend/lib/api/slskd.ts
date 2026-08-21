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

export type SlskdDaemonStatus = { reachable: boolean; owned: boolean | null; pid: number | null };

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

/** Scrive le credenziali Soulseek nel slskd.yml. La password non torna indietro. */
export function daemonConfig(body: {
  username: string; password: string; port?: number; download_dir?: string;
}) {
  return apiPut<{ configured: boolean; username: string }>("/api/slskd/daemon/config", body);
}
