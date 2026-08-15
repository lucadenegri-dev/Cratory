"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Music, ArrowRight } from "lucide-react";
import {
  apiGet, getPipeline,
  type LibraryStats, type SetlistSummary, type PipelineStatus, type Track,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { usePlayer } from "@/lib/player";
import { PipelineStrip } from "@/components/dashboard/pipeline";
import { Card, Alert, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { Figure } from "@/components/dashboard/figure";
import { AsciiDj } from "@/components/dashboard/ascii-dj";

/** «La Cabina»: le due griglie di orientamento e il DJ. Il ritratto statistico
 *  della libreria vive in /statistics, raggiunta dal link in alto. */
export default function Dashboard() {
  const t = useT();
  const player = usePlayer();
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [sets, setSets] = useState<SetlistSummary[] | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<LibraryStats>("/api/stats").then((s) => { setStats(s); setError(null); }).catch((e) => setError(String(e.message ?? e)));
    getPipeline().then(setPipeline).catch(() => setPipeline(null));
    apiGet<SetlistSummary[]>("/api/sets").then(setSets).catch(() => setSets([]));
  }, []);

  const empty = stats != null && stats.total_tracks === 0;

  /* Il click sulla consolle: una traccia posseduta a caso nel player docked.
     Offset casuale sul conteggio dei posseduti, una sola chiamata. */
  const playRandom = () => {
    const owned = stats?.with_local_file ?? 0;
    if (owned === 0) return;
    const offset = Math.floor(Math.random() * owned);
    apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      has_local_file: true, limit: 1, offset,
    })
      .then((r) => {
        const track = r.items[0];
        if (!track) return;
        player.play({
          kind: "local-track",
          track: {
            id: track.id,
            title: track.title ?? "",
            artist: track.artist ?? "",
            albumArtUrl: track.album_art_url ?? null,
            rating: track.rating ?? null,
          },
        });
      })
      .catch(() => {});
  };

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
          {/* Link alle statistiche: la pagina non ha header PageLayout, quindi
              il rimando sta qui, quieto e right-aligned sopra il frontespizio. */}
          <div className="mb-2 flex justify-end">
            <Link href="/statistics" className="text-[10px] uppercase tracking-wider text-muted transition-colors hover:text-fg">
              {t.dashboard.statsLink} →
            </Link>
          </div>

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

          {/* La consolle: puro carattere, in tutti i sensi. Premuta, suona. */}
          <div className="mt-12 flex justify-center overflow-x-auto">
            <AsciiDj onActivate={playRandom} label={t.dashboard.djPlayRandom} hint={t.dashboard.djHint} />
          </div>
        </>
      )}
    </PageLayout>
  );
}
