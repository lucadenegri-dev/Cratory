"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { LabelStats, LibraryStats } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Histogram } from "./histogram";

/* Riga di colophon: etichetta maiuscola a sinistra, contenuto in linea che
   tronca con ellissi. Una riga senza dati non viene resa: la decide il
   chiamante, qui non arrivano mai valori vuoti. */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline gap-4 overflow-hidden whitespace-nowrap py-1.5">
      <span className="w-20 shrink-0 text-[10px] uppercase tracking-wider text-muted">{label}</span>
      <span className="truncate text-sm text-fg">{children}</span>
    </div>
  );
}

/** Il ritratto della libreria compresso come il colophon di un volume: righe
 *  tipografiche tra due filetti, non grafici a colonne. */
export function Colophon({ stats, labels }: { stats: LibraryStats; labels: LabelStats[] }) {
  const t = useT();
  const keys = Object.entries(stats.key_distribution ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const genres = Object.entries(stats.genre_distribution ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 4);
  const tops = labels.slice(0, 3);
  const hasBpm = stats.bpm_min != null && stats.bpm_max != null;
  if (!hasBpm && keys.length === 0 && genres.length === 0 && tops.length === 0) return null;
  return (
    <div className="mt-6 divide-y divide-border border-y border-border">
      {hasBpm && (
        <Row label={t.dashboard.colophonBpm}>
          <span className="tnum text-fg-strong">{stats.bpm_min!.toFixed(0)}–{stats.bpm_max!.toFixed(0)}</span>
          <span className="ml-3 inline-block"><Histogram bins={stats.bpm_histogram} variant="spark" /></span>
        </Row>
      )}
      {keys.length > 0 && (
        <Row label={t.dashboard.colophonKeys}>
          {keys.map(([k, n]) => (
            <span key={k} className="mr-4">
              <span className="text-fg-strong">{k}</span>{" "}
              <span className="tnum text-muted">{n}</span>
            </span>
          ))}
        </Row>
      )}
      {genres.length > 0 && (
        <Row label={t.dashboard.colophonGenres}>
          {genres.map(([g, n]) => (
            <span key={g} className="mr-4">
              <Link href={`/library?genre=${encodeURIComponent(g)}`} className="text-fg-strong hover:underline">{g}</Link>{" "}
              <span className="tnum text-muted">{n}</span>
            </span>
          ))}
        </Row>
      )}
      {tops.length > 0 && (
        <Row label={t.dashboard.colophonLabels}>
          {tops.map((l) => (
            <span key={l.label} className="mr-4">
              <Link href={`/labels/${encodeURIComponent(l.label)}`} className="text-fg-strong hover:underline">{l.label}</Link>{" "}
              <span className="tnum text-muted">{l.track_count}</span>
            </span>
          ))}
        </Row>
      )}
    </div>
  );
}
