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
import { primeOnFirstGesture } from "@/lib/audio-analyser";
import { findTopPlaylist, pickRandom } from "@/lib/random-track";
import { PipelineStrip } from "@/components/dashboard/pipeline";
import { Alert, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { AsciiDj } from "@/components/dashboard/ascii-dj";
import { AsciiWordmark } from "@/components/dashboard/ascii-wordmark";
import { AsciiAtmosphere } from "@/components/dashboard/ascii-atmosphere";
import { SpectrumStrip } from "@/components/dashboard/spectrum-strip";

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
    // Sblocca il contesto Web Audio al primo gesto: dev'essere già in
    // esecuzione quando parte il primo `play`, altrimenti l'analizzatore non si
    // innesta e la cabina resta cieca proprio sulla traccia che l'ha avviata
    // (il trasporto monta dopo il click, troppo tardi per innescarlo da lì).
    primeOnFirstGesture();
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

  const owned = stats?.with_local_file ?? 0;
  const ownedPct = stats && stats.total_tracks > 0
    ? Math.round((owned / stats.total_tracks) * 100) : null;

  /* Il colophon in una riga sola: la scala della libreria in cifre tabellari,
     dove prima c'erano quattro celle riquadrate. Le playlist non ci sono: le
     conta già la prima fase della striscia qui sopra. */
  const colophon = stats && (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 text-[10px] uppercase tracking-wider text-muted">
      <span><span className="tnum text-fg-strong">{stats.total_tracks}</span> {t.dashboard.figureDiscovered}</span>
      <span className="text-faint">·</span>
      <span>
        <span className="tnum text-fg-strong">{owned}</span> {t.dashboard.figureOwned}
        {ownedPct !== null && <span className="tnum ml-1.5 text-faint">{ownedPct}%</span>}
      </span>
      <span className="text-faint">·</span>
      <span><span className="tnum text-fg-strong">{sets ? sets.length : "—"}</span> {t.dashboard.figureSets}</span>
      <Link href="/statistics" className="ml-auto transition-colors hover:text-fg-strong">
        {t.dashboard.statsLink} →
      </Link>
    </div>
  );

  return (
    <PageLayout>
      {/* Il frontespizio occupa la schermata: una sola composizione a piena
          altezza invece di tre lastre incorniciate dello stesso peso: erano
          quelle a impedire che la Home avesse un fuoco. La struttura la fanno
          i filetti (§4 di DESIGN.md), non i bordi delle Card.
          `container-type: size` solo da lg in su: sotto non c'è un'altezza
          definita e il contenimento farebbe collassare il blocco a zero. Le
          misure dell'arte in `cq*` discendono da qui — la cabina cresce fino a
          riempire quello che le resta. */}
      <div className="relative lg:h-[calc(100dvh-3rem-max(var(--player-bar-height,0px),106px))] lg:[container-type:size]">
        {/* L'aria di tutta la pagina, dietro alla composizione. Sta qui e non
            dentro il ramo dei dati così respira anche mentre carica e a
            libreria vuota. Il contenuto è posizionato e viene dopo nel DOM,
            quindi gli passa sopra senza bisogno di z-index. */}
        <AsciiAtmosphere active={player.audible} />

        <div className="relative flex h-full flex-col gap-3">
          <div className="flex-none">
            <AsciiWordmark sizeClass="text-[12px] sm:text-lg md:text-xl lg:text-[min(4.1cqh,4.5cqw)]" />
          </div>

          {error && <Alert tone="danger">{t.dashboard.backendDown(error)}</Alert>}

          {!stats && !error && <div className="flex flex-1 items-center justify-center"><Loading /></div>}

          {empty && (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
              <Music size={36} className="text-faint" />
              <div>
                <p className="font-medium text-fg-strong">{t.dashboard.emptyTitle}</p>
                <p className="mt-1 text-sm text-muted">{t.dashboard.emptyBody}</p>
              </div>
              <Link href="/playlists" className="inline-flex items-center gap-1.5 bg-fg-strong px-4 py-2 text-xs font-medium uppercase tracking-wider text-bg transition-colors hover:bg-fg">
                {t.dashboard.importPlaylist} <ArrowRight size={14} />
              </Link>
            </div>
          )}

          {stats && !empty && (
            <>
              {/* La cabina è il protagonista e si prende tutto lo spazio che
                  avanza. Suona premendola. Si muove solo mentre dall'app esce
                  davvero del suono (`audible`, non `status`: in pausa il dock
                  resta "playing"): a musica ferma la pagina è ferma, l'aria
                  della cabina e il pulviscolo di sfondo compresi. */}
              <div className="flex min-h-0 flex-1 items-center justify-center overflow-x-auto">
                <AsciiDj
                  animate={player.audible}
                  onActivate={playRandom}
                  label={t.dashboard.djPlayRandom}
                  sizeClass="text-[1.85vw] lg:text-[min(3.3cqh,2.1cqw)]"
                />
              </div>

              {/* Lo spettro, staccato dalla cabina: una striscia a piena
                  larghezza che chiude la zona dell'arte, sopra il piede. */}
              {/* `pt-4` oltre al gap della colonna: la striscia deve leggersi
                  come una misura autonoma, non come l'ultima riga della scena. */}
              <div className="flex-none px-1 pt-4">
                <SpectrumStrip active={player.audible} />
              </div>

              {/* Il piede: un filetto, le fasi del ciclo, il colophon in cifre. */}
              <div className="flex-none border-t border-border pt-1">
                {pipeline && <PipelineStrip p={pipeline} bare />}
                {colophon && <div className="border-t border-border px-4 py-2.5">{colophon}</div>}
              </div>
            </>
          )}
        </div>
      </div>
    </PageLayout>
  );
}
