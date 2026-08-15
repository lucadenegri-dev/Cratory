"use client";

import type { ReactNode } from "react";
import type { LabelStats, LibraryStats } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { EqMeter } from "@/components/ui";
import { Histogram } from "@/components/dashboard/histogram";
import { MiniBars, type MiniBarRow } from "@/components/dashboard/mini-bars";

/* Cella della griglia statistiche: titolo di sezione (10px maiuscolo) sopra il
   contenuto. La griglia esterna disegna i filetti; una sezione senza dati non
   viene resa (il chiamante filtra). */
function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="p-5">
      <h2 className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-fg-strong">{title}</h2>
      {children}
    </section>
  );
}

function CoverageRow({ label, value, total }: { label: string; value: number; total: number }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="w-32 shrink-0 truncate text-xs text-muted">{label}</span>
      <EqMeter value={pct} calm className="h-4 flex-1" />
      <span className="tnum w-10 shrink-0 text-right text-xs text-fg-strong">{pct}%</span>
    </div>
  );
}

/** Il ritratto completo della libreria: tutto ciò che il colophon della
 *  dashboard riassumeva, qui a grafici pieni. Solo presentazione: i dati
 *  arrivano già caricati dalla route. */
export function StatisticsView({ stats, labels }: { stats: LibraryStats; labels: LabelStats[] }) {
  const t = useT();

  const keyRows: MiniBarRow[] = Object.entries(stats.key_distribution ?? {})
    .sort((a, b) => b[1] - a[1])
    .map(([k, n]) => ({ label: k, value: n }));

  const genreRows: MiniBarRow[] = Object.entries(stats.genre_distribution ?? {})
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([g, n]) => ({ label: g, value: n, href: `/library?genre=${encodeURIComponent(g)}` }));

  const labelRows: MiniBarRow[] = labels.slice(0, 10).map((l) => ({
    label: l.label, value: l.track_count, href: `/labels/${encodeURIComponent(l.label)}`,
  }));

  const energyRows: MiniBarRow[] = (stats.energy_distribution ?? []).map((b) => ({
    label: `${b.from}–${b.to}`, value: b.count,
  }));

  const sourceRows: MiniBarRow[] = Object.entries(stats.by_source ?? {})
    .sort((a, b) => b[1] - a[1])
    .map(([s, n]) => ({ label: s, value: n }));

  const sections: ReactNode[] = [];

  if (stats.bpm_histogram.length > 0) {
    sections.push(
      <Section key="bpm" title={t.stats.bpm}>
        <Histogram bins={stats.bpm_histogram} />
      </Section>,
    );
  }
  if (keyRows.length > 0) {
    sections.push(
      <Section key="keys" title={t.stats.keys}>
        <MiniBars rows={keyRows} />
      </Section>,
    );
  }
  if (genreRows.length > 0) {
    sections.push(
      <Section key="genres" title={t.stats.genres}>
        <MiniBars rows={genreRows} />
      </Section>,
    );
  }
  if (labelRows.length > 0) {
    sections.push(
      <Section key="labels" title={t.stats.labels}>
        <MiniBars rows={labelRows} />
      </Section>,
    );
  }
  if (energyRows.length > 0) {
    sections.push(
      <Section key="energy" title={t.stats.energy}>
        <MiniBars rows={energyRows} />
      </Section>,
    );
  }
  if (sourceRows.length > 0) {
    sections.push(
      <Section key="sources" title={t.stats.sources}>
        <MiniBars rows={sourceRows} />
      </Section>,
    );
  }
  if (stats.total_tracks > 0) {
    sections.push(
      <Section key="coverage" title={t.stats.coverage}>
        <div className="space-y-2.5">
          <CoverageRow label={t.stats.coverageBpm} value={stats.with_bpm} total={stats.total_tracks} />
          <CoverageRow label={t.stats.coverageKey} value={stats.with_key} total={stats.total_tracks} />
          <CoverageRow label={t.stats.coverageReady} value={stats.ready_for_set} total={stats.total_tracks} />
        </div>
      </Section>,
    );
  }

  /* Filetti interni della griglia senza doppi bordi: ogni cella disegna solo
     top e left, la cornice esterna li completa. */
  return (
    <div className="grid border border-border sm:grid-cols-2 [&>section]:border-border [&>section]:border-t [&>section:first-child]:border-t-0 sm:[&>section:nth-child(2)]:border-t-0 sm:[&>section:nth-child(even)]:border-l">
      {sections}
    </div>
  );
}
