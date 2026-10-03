/** Ordinamento e filtri del pannello Materiale, tutti nel browser: il
 *  materiale arriva intero dal backend, quindi riordinarlo non costa una
 *  richiesta. Chi non ha il valore va sempre in fondo, in entrambi i versi. */

import type { MaterialItem } from "@/lib/api";
import { camelotRank, normalizeCamelot } from "@/lib/camelot";

export type MaterialSort = "playlist" | "key" | "bpm" | "added";
export type SortDir = "asc" | "desc";

export type MaterialFilters = {
  bpmMin: number | null;
  bpmMax: number | null;
  key: string | null;
};

/** Le aggiunte si guardano dalle piu' recenti; tonalita' e BPM salgono. */
export function defaultDir(sort: MaterialSort): SortDir {
  return sort === "added" ? "desc" : "asc";
}

/** Confronto con gli assenti in fondo: `dir` gira solo i presenti. */
function compare<T extends number | string>(a: T | null, b: T | null, dir: SortDir): number {
  if (a === null || b === null) return a === b ? 0 : a === null ? 1 : -1;
  if (a === b) return 0;
  return (a < b ? -1 : 1) * (dir === "asc" ? 1 : -1);
}

const rank = (it: MaterialItem) => {
  const r = camelotRank(it.track.camelot_key);
  return Number.isFinite(r) ? r : null;
};
const bpm = (it: MaterialItem) => it.track.bpm ?? null;
const added = (it: MaterialItem) => it.playlist_added_at ?? null;

/** Ordina una copia. I criteri di parita' salgono sempre (a parita' di
 *  tonalita' il BPM, a parita' di BPM la tonalita'), poi l'ordine del server. */
export function sortMaterial(items: MaterialItem[], sort: MaterialSort, dir: SortDir): MaterialItem[] {
  if (sort === "playlist") return [...items];
  const order = new Map(items.map((it, i) => [it, i]));
  const byKey = (a: MaterialItem, b: MaterialItem) => compare(rank(a), rank(b), dir) || compare(bpm(a), bpm(b), "asc");
  const byBpm = (a: MaterialItem, b: MaterialItem) => compare(bpm(a), bpm(b), dir) || compare(rank(a), rank(b), "asc");
  const byAdded = (a: MaterialItem, b: MaterialItem) => compare(added(a), added(b), dir);
  const by = sort === "key" ? byKey : sort === "bpm" ? byBpm : byAdded;
  return [...items].sort((a, b) => by(a, b) || (order.get(a) ?? 0) - (order.get(b) ?? 0));
}

/** BPM min e max inclusivi, tonalita' esatta. Con un filtro attivo chi non ha
 *  quel dato esce: «124–128» non puo' promettere una traccia senza BPM. */
export function filterMaterial(items: MaterialItem[], { bpmMin, bpmMax, key }: MaterialFilters): MaterialItem[] {
  const wanted = normalizeCamelot(key);
  return items.filter((it) => {
    const b = it.track.bpm;
    if (bpmMin !== null && (b == null || b < bpmMin)) return false;
    if (bpmMax !== null && (b == null || b > bpmMax)) return false;
    if (wanted !== null && normalizeCamelot(it.track.camelot_key) !== wanted) return false;
    return true;
  });
}
