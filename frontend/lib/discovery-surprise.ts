import { DEPTHS, type SeedType } from "@/lib/discovery-dig";

export type SurprisePick = { seedType: SeedType; value: string; depth: number };

// Una sola fonte per i valori di profondita': gli stessi di DEPTHS (surface/mid/deep).
const DEPTH_VALUES = DEPTHS.map((d) => d.value);

/**
 * Pesca un seme casuale dal gusto (libreria): generi di libreria + etichette,
 * pick uniforme, esclusi gli style curati. `exclude` (i semi già in barra)
 * viene escluso per non ripetere un colpo appena fatto; se non resta nulla,
 * ripesca comunque da tutto il pool. `rng` iniettabile per i test.
 */
export function pickSurprise(
  pool: { genres: string[]; labels: string[] },
  exclude: string[],
  rng: () => number = Math.random,
): SurprisePick | null {
  const entries: { seedType: SeedType; value: string }[] = [
    ...pool.genres.map((value) => ({ seedType: "genre" as const, value })),
    ...pool.labels.map((value) => ({ seedType: "label" as const, value })),
  ];
  if (entries.length === 0) return null;

  const cur = new Set(exclude.map((v) => v.trim().toLowerCase()).filter(Boolean));
  const filtered = cur.size ? entries.filter((e) => !cur.has(e.value.trim().toLowerCase())) : entries;
  const chooseFrom = filtered.length > 0 ? filtered : entries;

  const idx = Math.min(Math.floor(rng() * chooseFrom.length), chooseFrom.length - 1);
  const entry = chooseFrom[idx];
  const depth = DEPTH_VALUES[Math.min(Math.floor(rng() * DEPTH_VALUES.length), DEPTH_VALUES.length - 1)];
  return { seedType: entry.seedType, value: entry.value, depth };
}
