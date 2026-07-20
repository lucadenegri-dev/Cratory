import type { SeedType } from "@/components/discovery-dig-bar";

export type SurprisePick = { seedType: SeedType; value: string; depth: number };

// Gli stessi tre valori di DEPTHS in discovery-dig-bar (surface/mid/deep).
const DEPTH_VALUES = [0.0, 0.5, 1.0];

/**
 * Pesca un seme casuale dal gusto (libreria): generi di libreria + etichette,
 * pick uniforme, esclusi gli style curati. `current` (il seme in barra) viene
 * escluso per non ripetere il colpo appena fatto; se resta l'unico seme, lo
 * ripesca comunque. `rng` iniettabile per i test.
 */
export function pickSurprise(
  pool: { genres: string[]; labels: string[] },
  current: string | null,
  rng: () => number = Math.random,
): SurprisePick | null {
  const entries: { seedType: SeedType; value: string }[] = [
    ...pool.genres.map((value) => ({ seedType: "genre" as const, value })),
    ...pool.labels.map((value) => ({ seedType: "label" as const, value })),
  ];
  if (entries.length === 0) return null;

  const cur = current?.trim().toLowerCase() ?? null;
  const filtered = cur ? entries.filter((e) => e.value.trim().toLowerCase() !== cur) : entries;
  const chooseFrom = filtered.length > 0 ? filtered : entries;

  const idx = Math.min(Math.floor(rng() * chooseFrom.length), chooseFrom.length - 1);
  const entry = chooseFrom[idx];
  const depth = DEPTH_VALUES[Math.min(Math.floor(rng() * DEPTH_VALUES.length), DEPTH_VALUES.length - 1)];
  return { seedType: entry.seedType, value: entry.value, depth };
}
