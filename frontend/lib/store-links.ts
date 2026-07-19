// Link d'acquisto della wishlist: ricerche precompilate, si aprono in un'altra
// tab e l'acquisto avviene sul negozio. Niente API, niente chiavi (spec
// 2026-07-19): Cratory resta deterministico e offline-friendly.

export type StoreKey = "bandcamp" | "beatport" | "juno" | "discogs";

export const STORES: { key: StoreKey; label: string; url: (q: string) => string }[] = [
  { key: "bandcamp", label: "Bandcamp", url: (q) => `https://bandcamp.com/search?q=${q}` },
  { key: "beatport", label: "Beatport", url: (q) => `https://www.beatport.com/search?q=${q}` },
  { key: "juno", label: "Juno Download", url: (q) => `https://www.junodownload.com/search/?q%5Ball%5D%5B%5D=${q}` },
  { key: "discogs", label: "Discogs", url: (q) => `https://www.discogs.com/search/?q=${q}&type=release` },
];

export function storeQuery(artist: string | null, title: string | null): string {
  return encodeURIComponent([artist, title].filter(Boolean).join(" "));
}
