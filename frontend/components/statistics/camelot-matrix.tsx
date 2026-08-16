"use client";

import Link from "next/link";
import { useT } from "@/lib/i18n";

/* La ruota Camelot e' un ciclo, non una classifica: ordinare per conteggio (come
   faceva la lista di barre) ne distrugge la struttura. Qui le 24 tonalita'
   tornano nella loro griglia — 12 posizioni, lato A (minore) e lato B
   (maggiore) — con le barre speculari attorno al numero di posizione: righe
   adiacenti sono tonalita' armonicamente adiacenti, e lo squilibrio fra i due
   lati si legge in un colpo d'occhio. Scala condivisa fra A e B, altrimenti
   proprio quello squilibrio sparirebbe. */

const POSITIONS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

function Cell({ camelot, value, max, side }: {
  camelot: string; value: number; max: number; side: "minor" | "major";
}) {
  const t = useT();
  const pct = value > 0 ? Math.max(2, Math.round((value / max) * 100)) : 0;
  const count = (
    <span className={`tnum w-6 shrink-0 text-[11px] ${side === "minor" ? "text-right" : "text-left"} ${value > 0 ? "text-muted group-hover:text-fg-strong" : "text-faint"}`}>
      {value}
    </span>
  );
  const bar = (
    <span className="h-2.5 flex-1 bg-elevated">
      <span
        className={`block h-full bg-fg transition-colors group-hover:bg-fg-strong ${side === "minor" ? "ml-auto" : ""}`}
        style={{ width: `${pct}%` }}
      />
    </span>
  );
  return (
    <Link
      href={`/library?key=${encodeURIComponent(camelot)}`}
      aria-label={t.stats.keyTracks(camelot, value)}
      title={t.stats.keyTracks(camelot, value)}
      className="group flex items-center gap-2"
    >
      {side === "minor" ? <>{count}{bar}</> : <>{bar}{count}</>}
    </Link>
  );
}

export function CamelotMatrix({ distribution }: { distribution: Record<string, number> }) {
  const t = useT();
  const max = Math.max(1, ...Object.values(distribution));
  return (
    <div>
      <div className="mb-2 grid grid-cols-[1fr_1.5rem_1fr] gap-x-2 text-[10px] uppercase tracking-wider text-muted">
        <span className="text-right">{t.stats.keysMinor}</span>
        <span />
        <span>{t.stats.keysMajor}</span>
      </div>
      <div className="space-y-1.5">
        {POSITIONS.map((p) => (
          <div key={p} className="grid grid-cols-[1fr_1.5rem_1fr] items-center gap-x-2">
            <Cell camelot={`${p}A`} value={distribution[`${p}A`] ?? 0} max={max} side="minor" />
            <span className="tnum text-center text-[11px] text-fg-strong">{p}</span>
            <Cell camelot={`${p}B`} value={distribution[`${p}B`] ?? 0} max={max} side="major" />
          </div>
        ))}
      </div>
    </div>
  );
}
