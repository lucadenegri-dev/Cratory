import { API, apiGet, apiPost } from "./client";
import type { GenStatus, Setlist } from "./types";

/** Stato della generazione set in background: unico poller in JobsProvider. */
export function generateStatus() {
  return apiGet<GenStatus>("/api/sets/generate-status");
}

export async function exportSet(setId: number, format: "text" | "csv" | "markdown" | "m3u8"): Promise<string> {
  const res = await fetch(`${API}/api/sets/${setId}/export?format=${format}`, { method: "POST" });
  if (!res.ok) throw new Error(res.statusText);
  return res.text();
}

/** Aggiunge una traccia al set (A14): position 1-based, assente = append in coda. */
export function addTrackToSet(setId: number, trackId: number, position?: number) {
  return apiPost<Setlist>(`/api/sets/${setId}/tracks`, { track_id: trackId, position });
}
