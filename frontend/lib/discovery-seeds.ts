// I semi di uno scavo: un genere o un'etichetta per voce, fino a MAX_SEEDS.
// Vive in lib/ perché barra, pagina e URL parlino la stessa lingua senza che
// la lib importi da un componente (stesso criterio di discovery-dig.ts).

import type { DigSourceKey, SeedType } from "@/lib/discovery-dig";

export type DigSeed = { type: SeedType; value: string };

/** Rispecchia MAX_SEEDS del backend: oltre, la quota di finestra per seme
 *  (300 // n) smette di dire qualcosa. */
export const MAX_SEEDS = 4;

const TYPES: readonly SeedType[] = ["genre", "label"];

function clean(seed: DigSeed): DigSeed {
  return { type: seed.type, value: seed.value.trim() };
}

/** Identità di un seme: tipo + valore, case-insensitive. "Deep House" e
 *  "deep house" sono lo stesso seme; il genere "Warp" e l'etichetta "Warp" no. */
export function seedKey(seed: DigSeed): string {
  return `${seed.type}:${seed.value.trim().toLowerCase()}`;
}

export function sameSeeds(a: DigSeed[], b: DigSeed[]): boolean {
  return a.length === b.length && a.every((s, i) => seedKey(s) === seedKey(b[i]));
}

/** Aggiunge in coda. Un duplicato non entra e viene restituito (il chiamante
 *  lo fa lampeggiare invece di sdoppiarlo); al cap `full` è vero e la lista
 *  resta com'era. Un valore vuoto non è un seme. */
export function addSeed(
  list: DigSeed[],
  seed: DigSeed,
): { seeds: DigSeed[]; duplicate: DigSeed | null; full: boolean } {
  const next = clean(seed);
  if (!next.value) return { seeds: list, duplicate: null, full: false };
  const key = seedKey(next);
  const duplicate = list.find((s) => seedKey(s) === key) ?? null;
  if (duplicate) return { seeds: list, duplicate, full: false };
  if (list.length >= MAX_SEEDS) return { seeds: list, duplicate: null, full: true };
  return { seeds: [...list, next], duplicate: null, full: false };
}

export function removeSeed(list: DigSeed[], seed: DigSeed): DigSeed[] {
  const key = seedKey(seed);
  return list.filter((s) => seedKey(s) !== key);
}

/** `type:value,type:value`. I due punti e la virgola compaiono nei nomi veri
 *  («Nu-Disco, Italo»), quindi il valore si codifica PRIMA di comporre la
 *  lista: la sola codifica della query string li lascerebbe passare tali e
 *  quali e spezzerebbe il parsing. */
export function encodeSeeds(seeds: DigSeed[]): string {
  return seeds.map((s) => `${s.type}:${encodeURIComponent(s.value)}`).join(",");
}

/** Il rovescio di `encodeSeeds`. Splitta sul PRIMO `:` soltanto; scarta tipi
 *  che non siano genre/label, valori vuoti e codifiche rotte: la stringa
 *  arriva dall'URL, e chi lo scrive non è per forza l'app. Tronca al cap. */
export function parseSeeds(raw: string | null): DigSeed[] {
  if (!raw) return [];
  const out: DigSeed[] = [];
  for (const part of raw.split(",")) {
    const i = part.indexOf(":");
    if (i <= 0) continue;
    const type = part.slice(0, i) as SeedType;
    if (!TYPES.includes(type)) continue;
    let value: string;
    try {
      value = decodeURIComponent(part.slice(i + 1)).trim();
    } catch {
      continue;
    }
    if (!value) continue;
    const r = addSeed(out, { type, value });
    if (r.full) break;
    out.splice(0, out.length, ...r.seeds);
  }
  return out;
}

/** L'URL di uno scavo. Unica fonte per il bottone Scava, Sorprendimi e il reroll. */
export function digHref(
  pathname: string,
  seeds: DigSeed[],
  depth: number,
  source: DigSourceKey,
): string {
  const params = new URLSearchParams();
  params.set("seeds", encodeSeeds(seeds));
  params.set("depth", String(depth));
  params.set("source", source);
  return `${pathname}?${params.toString()}`;
}
