import { API, apiPatch } from "./client";
import type { SetlistSummary } from "./types";

/** Rinomina un set, qualunque sia il suo tipo. Risponde col riepilogo, lo
 *  stesso di `GET /api/sets`. Sta fuori dal protocollo delle revisioni dei set
 *  a mano: non manda `expected_revision` e non fa avanzare la revisione,
 *  perche' il nome non e' il percorso — due rinomine concorrenti si
 *  sovrascrivono senza rompere niente, e non devono invalidare le modifiche in
 *  corso sulle righe. Il nome vero e' quello che TORNA: il server lo ripulisce
 *  ai bordi e rifiuta con 422 quello di soli spazi. */
export function renameSet(id: number, name: string) {
  return apiPatch<SetlistSummary>(`/api/sets/${id}`, { name });
}

/** Export di un set GENERATO ancora in archivio: l'unico modo di portarselo via
 *  prima di cancellarlo, ora che non ha piu' una pagina di dettaglio. I set
 *  preparati a mano hanno il loro (lib/api/manual-sets.ts). */
export async function exportSet(setId: number, format: "text" | "csv" | "markdown" | "m3u8"): Promise<string> {
  const res = await fetch(`${API}/api/sets/${setId}/export?format=${format}`, { method: "POST" });
  if (!res.ok) throw new Error(res.statusText);
  return res.text();
}

