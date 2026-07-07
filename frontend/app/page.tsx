"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Music, Gauge, ArrowRight, Tags, KeyRound, Disc3,
} from "lucide-react";
import {
  apiGet, getLabels, getPipeline, listImportedPlaylists, fmtDate,
  type LibraryStats, type LabelStats, type SetlistSummary, type Playlist, type PipelineStatus,
} from "@/lib/api";
import { PipelineStrip } from "@/components/dashboard/pipeline";
import { Card, Alert, Progress, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { Figure } from "@/components/dashboard/figure";
import { Histogram } from "@/components/dashboard/histogram";
import { MiniBars, type MiniBarRow } from "@/components/dashboard/mini-bars";
import { RecentList, type RecentItem } from "@/components/dashboard/recent-list";

/* ----------------------------------------------------- helper di sezione */

function ColHead({ children }: { children: React.ReactNode }) {
  return <div className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-fg-strong">{children}</div>;
}

function SubLabel({ icon, children }: { icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="mb-2 mt-4 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted first:mt-0">
      {icon && <span className="text-faint">{icon}</span>}{children}
    </div>
  );
}

function Coverage({ label, n, total }: { label: string; n: number; total: number }) {
  const pct = total ? Math.round((n / total) * 100) : 0;
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs"><span className="text-muted">{label}</span><span className="tnum text-muted">{n}/{total} · {pct}%</span></div>
      <Progress value={pct} />
    </div>
  );
}

/* ------------------------------------------------------------------ page */

export default function Dashboard() {
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [labels, setLabels] = useState<LabelStats[]>([]);
  const [sets, setSets] = useState<SetlistSummary[] | null>(null);
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<LibraryStats>("/api/stats").then((s) => { setStats(s); setError(null); }).catch((e) => setError(String(e.message ?? e)));
    getPipeline().then(setPipeline).catch(() => setPipeline(null));
    getLabels().then(setLabels).catch(() => {});
    apiGet<SetlistSummary[]>("/api/sets").then(setSets).catch(() => setSets([]));
    listImportedPlaylists().then(setPlaylists).catch(() => setPlaylists([]));
  }, []);
  useEffect(load, [load]);

  const empty = stats != null && stats.total_tracks === 0;

  const keyRows: MiniBarRow[] = stats
    ? Object.entries(stats.key_distribution)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([k, n]) => ({ label: k, value: n }))
    : [];

  const genreRows: MiniBarRow[] = stats
    ? Object.entries(stats.genre_distribution ?? {})
        .sort((a, b) => b[1] - a[1])
        .slice(0, 6)
        .map(([g, n]) => ({ label: g, value: n, href: `/library?genre=${encodeURIComponent(g)}` }))
    : [];

  const labelRows: MiniBarRow[] = labels.slice(0, 5).map((l) => ({
    label: l.label, value: l.track_count, href: `/labels/${encodeURIComponent(l.label)}`,
  }));

  const recentSets: RecentItem[] = (sets ?? [])
    .slice()
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, 4)
    .map((s, i) => ({ n: String(i + 1).padStart(2, "0"), title: s.name, meta: fmtDate(s.created_at), href: `/sets/${s.id}` }));

  const recentPlaylists: RecentItem[] = (playlists ?? [])
    .slice()
    .sort((a, b) => (a.imported_at < b.imported_at ? 1 : -1))
    .slice(0, 3)
    .map((p, i) => ({ n: String(i + 1).padStart(2, "0"), title: p.name, meta: `${p.track_count} tr.`, href: `/playlists/${p.id}` }));

  return (
    <PageLayout>
      {error && <div className="mb-6"><Alert tone="danger">⚠ {error} — il backend è attivo su :8000?</Alert></div>}

      {!stats && !error && <Loading />}

      {empty && (
        <Card>
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <Music size={36} className="text-faint" />
            <div>
              <p className="font-medium text-fg-strong">Nessuna playlist ancora</p>
              <p className="mt-1 text-sm text-muted">Importa una playlist Spotify per iniziare a costruire un set.</p>
            </div>
            <Link href="/playlists" className="inline-flex items-center gap-1.5 bg-fg-strong px-4 py-2 text-xs font-medium uppercase tracking-wider text-bg transition-colors hover:bg-fg">
              Importa una playlist <ArrowRight size={14} />
            </Link>
          </div>
        </Card>
      )}

      {/* Striscia di orientamento: le sei fasi del ciclo con contatori vivi */}
      {!empty && pipeline && (
        <div className="mb-6">
          <PipelineStrip p={pipeline} onRefresh={load} />
        </div>
      )}

      {stats && !empty && (
        <>
          {/* Figure hero: scoperte (tutte le tracce note) ⊇ possedute (file su disco) */}
          <div className="grid grid-cols-2 border-l border-t border-border sm:grid-cols-4">
            <Figure label="Tracce scoperte" value={stats.total_tracks} />
            <Figure
              label="Tracce possedute"
              value={(
                <>
                  {stats.with_local_file}
                  {stats.total_tracks > 0 && (
                    <span className="ml-1.5 text-xs font-normal text-muted">
                      {Math.round((stats.with_local_file / stats.total_tracks) * 100)}%
                    </span>
                  )}
                </>
              )}
            />
            <Figure label="Playlist" value={stats.playlists} />
            <Figure label="Set salvati" value={sets ? sets.length : "—"} />
          </div>

          {/* Tre colonne */}
          <div className="mt-3 grid border border-border lg:grid-cols-3">
            <section className="border-b border-border p-5 lg:border-b-0 lg:border-r">
              <ColHead>Forma della libreria</ColHead>
              <SubLabel icon={<Gauge size={12} />}>Istogramma BPM{stats.bpm_min ? ` · ${stats.bpm_min.toFixed(0)}–${stats.bpm_max?.toFixed(0)}` : ""}</SubLabel>
              <Histogram bins={stats.bpm_histogram} />
              <SubLabel icon={<KeyRound size={12} />}>Tonalità più frequenti</SubLabel>
              <MiniBars rows={keyRows} />
            </section>

            <section className="border-b border-border p-5 lg:border-b-0 lg:border-r">
              <ColHead>Attività recente</ColHead>
              <div className="mb-2 flex items-center justify-between">
                <SubLabel>Ultimi set</SubLabel>
                <Link href="/sets" className="text-[10px] uppercase tracking-wider text-muted hover:text-fg">Tutti →</Link>
              </div>
              <RecentList items={recentSets} empty="Nessun set ancora." />
              <div className="mb-2 mt-5 flex items-center justify-between">
                <SubLabel>Ultime playlist importate</SubLabel>
                <Link href="/playlists" className="text-[10px] uppercase tracking-wider text-muted hover:text-fg">Tutte →</Link>
              </div>
              <RecentList items={recentPlaylists} empty="Nessuna playlist ancora." />
            </section>

            <section className="p-5">
              <ColHead>Catalogo</ColHead>
              <SubLabel icon={<Gauge size={12} />}>Copertura BPM/key · energia</SubLabel>
              <div className="space-y-2.5">
                <Coverage label="BPM e tonalità" n={stats.with_key} total={stats.total_tracks} />
                <Coverage label="Energia" n={stats.with_features} total={stats.total_tracks} />
              </div>
              <SubLabel icon={<Disc3 size={12} />}>Generi più frequenti</SubLabel>
              <MiniBars rows={genreRows} />
              <div className="mb-2 mt-5 flex items-center justify-between">
                <SubLabel icon={<Tags size={12} />}>Top etichette</SubLabel>
                <Link href="/labels" className="text-[10px] uppercase tracking-wider text-muted hover:text-fg">Tutte →</Link>
              </div>
              <MiniBars rows={labelRows} />
            </section>
          </div>
        </>
      )}
    </PageLayout>
  );
}
