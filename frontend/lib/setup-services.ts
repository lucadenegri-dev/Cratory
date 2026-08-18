import type { SecretKey } from "@/lib/api";

/** Quali credenziali servono a ciascun servizio. Dati, non JSX: la stessa
 *  mappa serve al wizard e alla pagina Impostazioni. */
export type ServiceKey = "spotify" | "anthropic" | "discogs" | "acoustid" | "slskd";

export const SERVICE_FIELDS: Record<ServiceKey, SecretKey[]> = {
  spotify: ["spotify_client_id", "spotify_client_secret"],
  anthropic: ["ai_api_key"],
  discogs: ["discogs_token"],
  acoustid: ["acoustid_api_key"],
  slskd: ["slskd_api_key"],
};

/** I servizi che hanno una prova reale lato backend. slskd no: il suo stato
 *  vivo arriva da GET /api/slskd/status. */
export const TESTABLE: ServiceKey[] = ["spotify", "anthropic", "discogs", "acoustid"];
