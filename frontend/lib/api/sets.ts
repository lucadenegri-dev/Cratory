import { API } from "./client";

/** Export di un set GENERATO ancora in archivio: l'unico modo di portarselo via
 *  prima di cancellarlo, ora che non ha piu' una pagina di dettaglio. I set
 *  preparati a mano hanno il loro (lib/api/manual-sets.ts). */
export async function exportSet(setId: number, format: "text" | "csv" | "markdown" | "m3u8"): Promise<string> {
  const res = await fetch(`${API}/api/sets/${setId}/export?format=${format}`, { method: "POST" });
  if (!res.ok) throw new Error(res.statusText);
  return res.text();
}

