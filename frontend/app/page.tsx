"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Music, ArrowRight } from "lucide-react";
import {
  apiGet, getLabels, getPipeline, downloadStatus, downloadPending,
  type LibraryStats, type LabelStats, type SetlistSummary, type PipelineStatus,
  type DownloadStatus, type Track,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { PipelineStrip } from "@/components/dashboard/pipeline";
import { Card, Alert, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { Figure } from "@/components/dashboard/figure";
import { Colophon } from "@/components/dashboard/colophon";
import { OpenWork, queuesActive } from "@/components/dashboard/open-work";

export default function Dashboard() {
  const t = useT();
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [labels, setLabels] = useState<LabelStats[]>([]);
  const [sets, setSets] = useState<SetlistSummary[] | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [download, setDownload] = useState<DownloadStatus | null>(null);
  const [pending, setPending] = useState<Track[]>([]);
  const [leads, setLeads] = useState<Track[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<LibraryStats>("/api/stats").then((s) => { setStats(s); setError(null); }).catch((e) => setError(String(e.message ?? e)));
    getPipeline().then(setPipeline).catch(() => setPipeline(null));
    getLabels().then(setLabels).catch(() => {});
    apiGet<SetlistSummary[]>("/api/sets").then(setSets).catch(() => setSets([]));
    downloadStatus().then(setDownload).catch(() => setDownload(null));
    downloadPending().then(setPending).catch(() => setPending([]));
    apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      sort: "added_at", order: "desc", has_local_file: false, limit: 5,
    }).then((r) => setLeads(r.items)).catch(() => setLeads([]));
  }, []);
  useEffect(load, [load]);

  /* Vivo solo sulle code: finché un download gira, download e pipeline si
     riaggiornano; le cifre del frontespizio restano l'istantanea iniziale,
     così la pagina respira senza sfarfallare. */
  const active = queuesActive(download, pipeline);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => {
      downloadStatus().then(setDownload).catch(() => {});
      getPipeline().then(setPipeline).catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [active]);

  const empty = stats != null && stats.total_tracks === 0;

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

      {stats && !empty && (
        <>
          {/* Frontespizio: le quattro misure come apertura tipografica. */}
          <div className="grid grid-cols-2 border-l border-t border-border sm:grid-cols-4">
            <Figure big label={t.dashboard.figureDiscovered} value={stats.total_tracks} />
            <Figure
              big
              label={t.dashboard.figureOwned}
              value={(
                <>
                  {stats.with_local_file}
                  {stats.total_tracks > 0 && (
                    <span className="ml-2 text-sm font-normal text-muted">
                      {Math.round((stats.with_local_file / stats.total_tracks) * 100)}%
                    </span>
                  )}
                </>
              )}
            />
            <Figure big label={t.dashboard.figurePlaylists} value={stats.playlists} />
            <Figure big label={t.dashboard.figureSets} value={sets ? sets.length : "—"} />
          </div>

          {/* Striscia di orientamento: le fasi del ciclo con contatori vivi. */}
          {pipeline && (
            <div className="mt-6">
              <PipelineStrip p={pipeline} />
            </div>
          )}

          {/* Il banco: il lavoro aperto sulla catena di acquisizione. */}
          <OpenWork download={download} pending={pending} inboxFiles={pipeline?.inbox_files ?? null} leads={leads} />

          {/* Il colophon: il ritratto della libreria in righe tipografiche. */}
          <Colophon stats={stats} labels={labels} />
        </>
      )}
    </PageLayout>
  );
}
