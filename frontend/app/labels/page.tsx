"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Users, Disc3 } from "lucide-react";
import { apiGet, getLabels, type LabelStats, type LibraryStats } from "@/lib/api";
import { Alert, EmptyState, Badge, Card, Input, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { MiniBars, type MiniBarRow } from "@/components/dashboard/mini-bars";

export default function Labels() {
  const [labels, setLabels] = useState<LabelStats[] | null>(null);
  const [genres, setGenres] = useState<Record<string, number>>({});
  const [error, setError] = useState<string | null>(null);
  const [qLabel, setQLabel] = useState("");
  const [qArtist, setQArtist] = useState("");
  const [qGenre, setQGenre] = useState("");

  const load = useCallback(() => {
    getLabels().then(setLabels).catch((e) => setError(String(e.message ?? e)));
    apiGet<LibraryStats>("/api/stats").then((s) => setGenres(s.genre_distribution ?? {})).catch(() => {});
  }, []);

  useEffect(load, [load]);

  const filtered = useMemo(() => {
    const inc = (v: string, q: string) => v.toLowerCase().includes(q.toLowerCase());
    return (labels ?? []).filter((l) =>
      (!qLabel || inc(l.label, qLabel)) &&
      (!qArtist || l.artists.some((a) => inc(a, qArtist))) &&
      (!qGenre || l.genres.some((g) => inc(g, qGenre))),
    );
  }, [labels, qLabel, qArtist, qGenre]);

  const total = filtered.reduce((s, l) => s + l.track_count, 0);

  const genreRows: MiniBarRow[] = Object.entries(genres)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map(([g, n]) => ({ label: g, value: n, href: `/library?genre=${encodeURIComponent(g)}` }));

  const marginalia = (
    <div className="space-y-4">
      <div className="space-y-2">
        <Input className="h-9" placeholder="Etichetta" value={qLabel} onChange={(e) => setQLabel(e.target.value)} />
        <Input className="h-9" placeholder="Artista" value={qArtist} onChange={(e) => setQArtist(e.target.value)} />
        <Input className="h-9" placeholder="Genere" value={qGenre} onChange={(e) => setQGenre(e.target.value)} />
      </div>
      {labels && (
        <div className="space-y-2 border-t border-border pt-4 text-xs">
          <div className="flex justify-between gap-2"><span className="text-muted">Etichette</span><span className="tnum text-fg">{filtered.length}</span></div>
          <div className="flex justify-between gap-2"><span className="text-muted">Tracce</span><span className="tnum text-fg">{total}</span></div>
        </div>
      )}
      {genreRows.length > 0 && (
        <div className="border-t border-border pt-4">
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">Generi in libreria</div>
          <MiniBars rows={genreRows} />
        </div>
      )}
    </div>
  );

  return (
    <PageLayout title="Etichette" meta={labels ? `${labels.length}` : undefined} marginaliaTitle="Panoramica" marginalia={marginalia}>
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {labels === null && !error && <Loading />}

      {labels && labels.length === 0 && (
        <EmptyState icon={<Disc3 size={28} />} title="Nessuna etichetta">
          Le tracce non hanno ancora l&apos;informazione sull&apos;etichetta. La label viene
          letta dal tag del file (scritto da DjOrganizer) durante l&apos;indicizzazione.
        </EmptyState>
      )}

      {labels && labels.length > 0 && filtered.length === 0 && (
        <p className="py-10 text-center text-sm text-muted">Nessuna etichetta con questi filtri.</p>
      )}

      {filtered.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((l) => {
            const years = l.year_min ? (l.year_max && l.year_max !== l.year_min ? `${l.year_min}–${l.year_max}` : `${l.year_min}`) : null;
            return (
              <Link key={l.label} href={`/labels/${encodeURIComponent(l.label)}`}>
                <Card className="h-full p-4 transition-colors hover:bg-elevated/40">
                  <div className="flex items-start justify-between gap-2">
                    <h2 className="min-w-0 truncate font-semibold text-fg-strong" title={l.label}>{l.label}</h2>
                    <Badge tone="neutral">{l.track_count}</Badge>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                    <span className="inline-flex items-center gap-1"><Disc3 size={13} /> {l.track_count} tracce</span>
                    <span className="inline-flex items-center gap-1"><Users size={13} /> {l.artist_count} artisti</span>
                    {years && <span>{years}</span>}
                  </div>
                  {l.genres.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {l.genres.map((g) => <Badge key={g} tone="neutral">{g}</Badge>)}
                    </div>
                  )}
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </PageLayout>
  );
}
