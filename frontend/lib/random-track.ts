import type { Playlist } from "@/lib/api";

/** Il nome della playlist da cui la consolle pesca. */
export const TOP_PLAYLIST_NAME = "top";

/** La playlist "Top", cercata per nome senza distinzione di maiuscole né spazi
 *  di contorno: l'utente la rinomina liberamente, non si cabla un id. `null`
 *  se non esiste — chi chiama decide il ripiego. */
export function findTopPlaylist(playlists: Playlist[]): Playlist | null {
  return playlists.find((p) => p.name.trim().toLowerCase() === TOP_PLAYLIST_NAME) ?? null;
}

/** Un elemento a caso, o `null` se la lista è vuota. `rnd` è iniettabile per
 *  i test (di default `Math.random`). */
export function pickRandom<T>(items: T[], rnd: () => number = Math.random): T | null {
  if (items.length === 0) return null;
  return items[Math.floor(rnd() * items.length)] ?? null;
}
