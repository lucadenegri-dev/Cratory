import { apiGet, apiPost } from "./client";
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
