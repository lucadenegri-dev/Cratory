import type { Dictionary } from "@/lib/i18n";

// Etichetta di provenienza di un file locale candidato (libreria posseduta
// vs. cartella download), usata dai modali di collegamento traccia<->file.
export function sourceLabel(t: Dictionary): Record<string, string> {
  return { library: t.tracks.sourceLibrary, downloads: t.tracks.sourceDownloads };
}
