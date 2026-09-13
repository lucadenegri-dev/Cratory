import type { Track } from "./types";
import { DICTIONARIES, getCurrentLanguage } from "@/lib/i18n/runtime";

// Locale per le date: "it" -> it-IT, "en" -> en-GB (non en-US). Scelta
// deliberata, non l'inglese "neutro": l'utenza e' italiana anche quando
// legge la UI in inglese, quindi l'ordine giorno/mese/anno resta quello
// atteso (en-US userebbe mese/giorno/anno). Stessa mappatura gia' in uso
// per l'omonimo `fmtDate` di lib/organize/api.ts.
function dateLocale(): string {
  return getCurrentLanguage() === "it" ? "it-IT" : "en-GB";
}

export function trackLabel(t: Track): string {
  const dict = DICTIONARIES[getCurrentLanguage()];
  const artist = t.artist?.trim() || dict.tracks.unknownArtist;
  const title = t.title?.trim() || dict.tracks.untitledHeading;
  return `${artist} — ${title}`;
}

export function fmtSize(bytes: number | null): string {
  if (!bytes) return "";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function fmtDuration(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Durata lunga (totali di playlist): "3h 21min" sopra l'ora, "42 min" sotto. */
export function fmtDurationLong(seconds: number | null | undefined): string {
  if (!seconds) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${String(m).padStart(2, "0")}min` : `${m} min`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(dateLocale(), { day: "2-digit", month: "short", year: "numeric" });
}

// Variante compatta per le tabelle tracce (vincolo: niente scroll orizzontale).
export function fmtDateShort(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(dateLocale(), { day: "2-digit", month: "2-digit", year: "2-digit" });
}
