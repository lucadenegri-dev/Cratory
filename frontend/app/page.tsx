"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Music, Gauge, ArrowRight, Tags, KeyRound, Disc3, AlertTriangle,
} from "lucide-react";
import {
  apiGet, getLabels, getPipeline, listImportedPlaylists, libraryGaps, fmtDate,
  type LibraryStats, type LabelStats, type SetlistSummary, type Playlist, type PipelineStatus, type GapAnalysis,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { PipelineStrip } from "@/components/dashboard/pipeline";
import { Card, Alert, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { Figure } from "@/components/dashboard/figure";
import { Histogram } from "@/components/dashboard/histogram";
import { MiniBars, type MiniBarRow } from "@/components/dashboard/mini-bars";
import { RecentList, type RecentItem } from "@/components/dashboard/recent-list";
import { GapsList } from "@/components/dashboard/gaps-list";

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

/* ------------------------------------------------------------------ page */

export default function Dashboard() {
  const t = useT();
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [labels, setLabels] = useState<LabelStats[]>([]);
  const [sets, setSets] = useState<SetlistSummary[] | null>(null);
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [gaps, setGaps] = useState<GapAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<LibraryStats>("/api/stats").then((s) => { setStats(s); setError(null); }).catch((e) => setError(String(e.message ?? e)));
    getPipeline().then(setPipeline).catch(() => setPipeline(null));
    getLabels().then(setLabels).catch(() => {});
    apiGet<SetlistSummary[]>("/api/sets").then(setSets).catch(() => setSets([]));
    listImportedPlaylists().then(setPlaylists).catch(() => setPlaylists([]));
    libraryGaps().then(setGaps).catch(() => setGaps(null));
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
    .map((p, i) => ({ n: String(i + 1).padStart(2, "0"), title: p.name, meta: t.dashboard.tracksAbbrev(p.track_count), href: `/playlists/${p.id}` }));

  return (
    <PageLayout>
      {error && <div className="mb-6"><Alert tone="danger">{t.dashboard.backendDown(error)}</Alert></div>}

      {!stats && !error && <Loading />}

      {empty && (
        <Card>
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <Music size={36} className="text-faint" />
            <div>
              <p className="font-medium text-fg-strong">{t.dashboard.emptyTitle}</p>
              <p className="mt-1 text-sm text-muted">{t.dashboard.emptyBody}</p>
            </div>
            <Link href="/playlists" className="inline-flex items-center gap-1.5 bg-fg-strong px-4 py-2 text-xs font-medium uppercase tracking-wider text-bg transition-colors hover:bg-fg">
              {t.dashboard.importPlaylist} <ArrowRight size={14} />
            </Link>
          </div>
        </Card>
      )}

      {/* Striscia di orientamento: le sei fasi del ciclo con contatori vivi */}
      {!empty && pipeline && (
        <div className="mb-6">
          <PipelineStrip p={pipeline} />
        </div>
      )}

      {stats && !empty && (
        <>
          {/* Figure hero: scoperte (tutte le tracce note) ⊇ possedute (file su disco) */}
          <div className="grid grid-cols-2 border-l border-t border-border sm:grid-cols-4">
            <Figure label={t.dashboard.figureDiscovered} value={stats.total_tracks} />
            <Figure
              label={t.dashboard.figureOwned}
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
            <Figure label={t.dashboard.figurePlaylists} value={stats.playlists} />
            <Figure label={t.dashboard.figureSets} value={sets ? sets.length : "—"} />
          </div>

          {/* Tre colonne */}
          <div className="mt-3 grid border border-border lg:grid-cols-3">
            <section className="border-b border-border p-5 lg:border-b-0 lg:border-r">
              <ColHead>{t.dashboard.libraryShape}</ColHead>
              <SubLabel icon={<Gauge size={12} />}>{t.dashboard.bpmHistogram}{stats.bpm_min ? ` · ${stats.bpm_min.toFixed(0)}–${stats.bpm_max?.toFixed(0)}` : ""}</SubLabel>
              <Histogram bins={stats.bpm_histogram} />
              <SubLabel icon={<KeyRound size={12} />}>{t.dashboard.topKeys}</SubLabel>
              <MiniBars rows={keyRows} />
            </section>

            <section className="border-b border-border p-5 lg:border-b-0 lg:border-r">
              <ColHead>{t.dashboard.recentActivity}</ColHead>
              <div className="mb-2 flex items-center justify-between">
                <SubLabel>{t.dashboard.recentSets}</SubLabel>
                <Link href="/sets" className="text-[10px] uppercase tracking-wider text-muted hover:text-fg">{t.dashboard.viewAllMasculine}</Link>
              </div>
              <RecentList items={recentSets} empty={t.dashboard.noSetsYet} />
              <div className="mb-2 mt-5 flex items-center justify-between">
                <SubLabel>{t.dashboard.recentPlaylistsHeading}</SubLabel>
                <Link href="/playlists" className="text-[10px] uppercase tracking-wider text-muted hover:text-fg">{t.dashboard.viewAllFeminine}</Link>
              </div>
              <RecentList items={recentPlaylists} empty={t.dashboard.noPlaylistsYet} />
            </section>

            <section className="p-5">
              <ColHead>{t.dashboard.catalog}</ColHead>
              <SubLabel icon={<Disc3 size={12} />}>{t.dashboard.topGenres}</SubLabel>
              <MiniBars rows={genreRows} />
              <div className="mb-2 mt-5 flex items-center justify-between">
                <SubLabel icon={<Tags size={12} />}>{t.dashboard.topLabels}</SubLabel>
                <Link href="/labels" className="text-[10px] uppercase tracking-wider text-muted hover:text-fg">{t.dashboard.viewAllFeminine}</Link>
              </div>
              <MiniBars rows={labelRows} />

              {/* Card visibile solo se ci sono lacune: niente testo segnaposto in dashboard. */}
              {gaps && gaps.gaps.length > 0 && (
                <>
                  <SubLabel icon={<AlertTriangle size={12} />}>{t.dashboard.libraryGaps}</SubLabel>
                  <GapsList gaps={gaps.gaps} empty={t.dashboard.noStructuralGaps} />
                </>
              )}
            </section>
          </div>
        </>
      )}
    </PageLayout>
  );
}
