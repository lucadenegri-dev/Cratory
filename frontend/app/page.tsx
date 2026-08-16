"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Music, ArrowRight } from "lucide-react";
import {
  apiGet, getPipeline, listImportedPlaylists,
  type LibraryStats, type SetlistSummary, type PipelineStatus, type Track, type Playlist,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { usePlayer } from "@/lib/player";
import { findTopPlaylist, pickRandom } from "@/lib/random-track";
import { PipelineStrip } from "@/components/dashboard/pipeline";
import { Card, Alert, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { Figure } from "@/components/dashboard/figure";
import { AsciiDj } from "@/components/dashboard/ascii-dj";
import { AsciiWordmark } from "@/components/dashboard/ascii-wordmark";

/** La Home: il frontespizio (il nome in grande e la consolle che suona), poi
 *  la striscia del ciclo e le quattro misure in chiusura. Il ritratto
 *  statistico della libreria vive in /statistics. */
export default function Home() {
  const t = useT();
  const player = usePlayer();
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [sets, setSets] = useState<SetlistSummary[] | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<LibraryStats>("/api/stats").then((s) => { setStats(s); setError(null); }).catch((e) => setError(String(e.message ?? e)));
    getPipeline().then(setPipeline).catch(() => setPipeline(null));
    apiGet<SetlistSummary[]>("/api/sets").then(setSets).catch(() => setSets([]));
    // Serve solo a risolvere la playlist "Top" da cui pesca la consolle.
    listImportedPlaylists().then(setPlaylists).catch(() => setPlaylists([]));
  }, []);

  const empty = stats != null && stats.total_tracks === 0;

  /* Il click sulla consolle: una traccia a caso dalla playlist "Top", fra
     quelle possedute (solo quelle hanno un file da suonare). Se la playlist
     non esiste si ripiega su tutta la libreria posseduta. `limit: 0` = tutte,
     così la scelta è casuale davvero e basta una chiamata. */
  const playRandom = () => {
    if ((stats?.with_local_file ?? 0) === 0) return;
    const top = findTopPlaylist(playlists);
    apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      has_local_file: true,
      limit: 0,
      ...(top ? { in_playlist: [top.id] } : {}),
    })
      .then((r) => {
        const track = pickRandom(r.items);
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
      {/* Il frontespizio sta in cima sempre: anche a libreria vuota e mentre
          carica, la Home ha una testata. Sotto cambia solo il contenuto. */}
      <div className="mb-3">
        <AsciiWordmark />
      </div>

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
          {/* La consolle chiude il frontespizio, sotto il nome: puro carattere,
              in tutti i sensi. Premuta, suona. Si muove solo mentre dall'app
              esce davvero del suono (`audible`, non `status`: in pausa il dock
              resta "playing").
              Incorniciata nello stesso involucro delle due sezioni sotto
              (Card: bordo pieno e fondo surface): le tre lastre si leggono
              come una serie invece che come un disegno sospeso nel vuoto. */}
          <Card>
            <div className="flex justify-center overflow-x-auto px-3 py-1">
              <AsciiDj
                animate={player.audible}
                onActivate={playRandom}
                label={t.dashboard.djPlayRandom}
                hint={t.dashboard.djHint}
              />
            </div>
          </Card>

          {/* Link alle statistiche: la pagina non ha header PageLayout, quindi
              il rimando sta qui, quieto e right-aligned in testa alle due
              sezioni di dati a cui appartiene — non sopra il frontespizio. */}
          <div className="mb-0.5 mt-1.5 flex justify-end">
            <Link href="/statistics" className="text-[10px] uppercase tracking-wider text-muted transition-colors hover:text-fg">
              {t.dashboard.statsLink} →
            </Link>
          </div>

          {/* Striscia di orientamento: le fasi del ciclo con contatori vivi. */}
          {pipeline && <PipelineStrip p={pipeline} />}

          {/* Le quattro misure chiudono la pagina, come un colophon in cifre.
              Stesso involucro della striscia sopra (Card: fondo surface e
              bordo pieno); il margine negativo fa uscire i filetti di chiusura
              delle celle di bordo, che `overflow-hidden` ritaglia — così le
              divisioni interne restano da 1px a ogni breakpoint. */}
          <div className="-mt-px overflow-hidden border border-border bg-surface">
            <div className="-mb-px -mr-px grid grid-cols-2 sm:grid-cols-4">
              <Figure label={t.dashboard.figureDiscovered} value={stats.total_tracks} />
              <Figure
                label={t.dashboard.figureOwned}
                value={(
                  <>
                    {stats.with_local_file}
                    {stats.total_tracks > 0 && (
                      <span className="ml-1.5 text-[10px] font-normal text-muted">
                        {Math.round((stats.with_local_file / stats.total_tracks) * 100)}%
                      </span>
                    )}
                  </>
                )}
              />
              <Figure label={t.dashboard.figurePlaylists} value={stats.playlists} />
              <Figure label={t.dashboard.figureSets} value={sets ? sets.length : "—"} />
            </div>
          </div>
        </>
      )}
    </PageLayout>
  );
}
