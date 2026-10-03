/** La ruota Camelot: 1A, 1B, 2A, 2B … 12B. L'ordine alfabetico della stringa
 *  ("10A" prima di "1A") non serve a nessuno che mixi. */

const CAMELOT = /^\s*(\d{1,2})\s*([ABab])\s*$/;

export const CAMELOT_KEYS: string[] = Array.from({ length: 12 }, (_, i) => [`${i + 1}A`, `${i + 1}B`]).flat();

/** Posizione sulla ruota; +Infinity per una tonalita' assente o illeggibile.
 *  Chi ordina decide da se' dove mandare gli sconosciuti. */
export function camelotRank(key: string | null): number {
  const m = key ? CAMELOT.exec(key) : null;
  if (!m) return Number.POSITIVE_INFINITY;
  return Number(m[1]) * 2 + (m[2].toUpperCase() === "B" ? 1 : 0);
}

/** "8a" -> "8A"; null se non e' una delle 24 tonalita'. */
export function normalizeCamelot(key: string | null): string | null {
  const m = key ? CAMELOT.exec(key) : null;
  if (!m) return null;
  const n = Number(m[1]);
  return n >= 1 && n <= 12 ? `${n}${m[2].toUpperCase()}` : null;
}
