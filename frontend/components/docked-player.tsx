"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Check, Plus, X } from "lucide-react";

import { apiGet, discoverySaveForLater, trackAudioUrl, type TrackDetail } from "@/lib/api";
import { KeyBadge } from "@/components/key-badge";
import { PlayerTransport } from "@/components/player-transport";
import { RatingDiamond } from "@/components/rating-diamond";
import { TrackCover } from "@/components/track-cover";
import { useT } from "@/lib/i18n";
import { usePlayer } from "@/lib/player";

export function DockedPlayer() {
  const { active, status, data, stop, setAudible, hasPrev, hasNext, prev, next } = usePlayer();
  const t = useT();
  // Stati effimeri del dock: errore di riproduzione locale (formato non
  // supportato / file sparito) e stato dell'azione ADD per la preview discovery.
  // Niente useEffect: l'azzeramento al cambio sorgente avviene "durante il
  // render" (pattern React consigliato per derivare stato da un prop che
  // cambia), evitando il render extra di un setState sincrono dentro un effect.
  const [localError, setLocalError] = useState(false);
  const [savingAdd, setSavingAdd] = useState(false);
  const [addedKey, setAddedKey] = useState<string | null>(null);
  // I tre dati da DJ della traccia in ascolto (BPM, tonalità, genere), presi
  // dalla scheda: LocalTrack porta solo l'identità, e caricarli qui evita di
  // allargare ogni chiamata play() dell'app.
  const [meta, setMeta] = useState<{ bpm: number | null; camelot: string | null; genre: string | null } | null>(null);

  const activeLocalId = active?.kind === "local-track" ? active.track.id : null;
  const activePreviewKey = active?.kind === "discovery-preview" ? active.item.key : null;
  const activeKey = active
    ? active.kind === "local-track"
      ? `l:${activeLocalId}`
      : `p:${activePreviewKey}`
    : null;
  const [prevKey, setPrevKey] = useState(activeKey);
  if (activeKey !== prevKey) {
    setPrevKey(activeKey);
    setLocalError(false);
    setSavingAdd(false);
    setMeta(null); // i dati della traccia precedente non devono trapelare sulla nuova
  }

  const visible = !!active && status !== "idle";
  const barRef = useRef<HTMLDivElement>(null);

  // Altezza pubblicata in --player-bar-height (pattern di --jobs-bar-height):
  // editorial-shell la usa come padding-bottom del <main>, così l'ultima riga
  // delle liste non resta coperta dalla barra. Senza deps: il contenuto della
  // barra (trasporto/messaggi/video) ne cambia l'altezza tra un render e l'altro.
  useEffect(() => {
    const h = visible ? (barRef.current?.offsetHeight ?? 0) : 0;
    document.documentElement.style.setProperty("--player-bar-height", `${h}px`);
  });
  useEffect(
    () => () => {
      document.documentElement.style.setProperty("--player-bar-height", "0px");
    },
    [],
  );

  useEffect(() => {
    if (activeLocalId == null) return;
    let cancelled = false;
    apiGet<TrackDetail>(`/api/tracks/${activeLocalId}`)
      .then((tr) => { if (!cancelled) setMeta({ bpm: tr.bpm, camelot: tr.camelot_key, genre: tr.genre }); })
      .catch(() => {}); // senza scheda il dock resta com'era: niente riga metadati
    return () => { cancelled = true; };
  }, [activeLocalId]);

  const prevNext = useMemo(
    () => (hasPrev || hasNext ? { hasPrev, hasNext, onPrev: prev, onNext: next } : null),
    [hasPrev, hasNext, prev, next],
  );

  // Metadata per il Now Playing di sistema (consumati dal trasporto, Task 4).
  const mediaMeta = useMemo(() => {
    if (!active) return null;
    return active.kind === "local-track"
      ? { title: active.track.title, artist: active.track.artist, artworkUrl: active.track.albumArtUrl ?? null }
      : { title: active.item.title, artist: active.item.artist, artworkUrl: active.item.addInput?.album_art_url ?? null };
  }, [active]);

  if (!active || status === "idle") return null;

  const title = active.kind === "local-track" ? active.track.title : active.item.title;
  const artist = active.kind === "local-track" ? active.track.artist : active.item.artist;

  // Miniatura: per la traccia posseduta l'artwork Spotify o la cover embedded
  // (via TrackCover); per la preview discovery la thumb del lead. `key` rimonta
  // TrackCover al cambio sorgente, azzerando il suo stato di fallback.
  const coverArt =
    active.kind === "local-track"
      ? { id: active.track.id, album_art_url: active.track.albumArtUrl ?? null, has_local_file: true }
      : { id: 0, album_art_url: active.item.addInput?.album_art_url ?? null, has_local_file: false };

  const addInput = active.kind === "discovery-preview" ? active.item.addInput : undefined;
  const isAdded = addedKey != null && addedKey === activePreviewKey;
  const onAdd = async () => {
    if (!addInput || !activePreviewKey || savingAdd || isAdded) return;
    setSavingAdd(true);
    try {
      await discoverySaveForLater(addInput);
      setAddedKey(activePreviewKey);
    } catch {
      // Silenzioso: l'utente può ritentare (l'errore non blocca l'ascolto).
    } finally {
      setSavingAdd(false);
    }
  };

  // Traccia posseduta = ha una scheda: cover e titolo ci portano. Le preview
  // discovery non sono in libreria, quindi restano testo.
  const trackHref = active.kind === "local-track" ? `/tracks?id=${active.track.id}` : null;

  return (
    // Telaio di posizionamento: `bottom` dinamico (se la barra job globale è
    // visibile pubblica la sua altezza in `--jobs-bar-height`, così il player le
    // sta sopra invece di sovrapporsi) e, da lg in su, i confini della colonna
    // contenuti — parte al bordo destro della nav (180px, come
    // lg:grid-cols-[180px_1fr] in editorial-shell) e si ferma alla colonna
    // marginale quando la pagina ne ha una (--content-aside-width, pubblicata da
    // PageLayout; 0px dove la colonna non c'è). Sotto lg le colonne sono
    // impilate: tutta larghezza. Il padding del telaio è lo stacco del pannello
    // fluttuante; `pointer-events-none` evita che quella cornice trasparente
    // rubi i click al contenuto sotto.
    <div
      ref={barRef}
      style={{ bottom: "var(--jobs-bar-height, 0px)" }}
      className="pointer-events-none fixed left-0 right-0 z-[60] p-2 sm:p-3 lg:left-[180px] lg:right-[var(--content-aside-width,0px)]"
    >
      {/* Il pannello: bordato sui quattro lati, un gradino tonale sopra il
          contenuto (elevated) e l'ombra concessa dalla Hairline Rule ai livelli
          che fluttuano sopra ciò che non possiedono. `relative` è il riferimento
          della timeline (assoluta) e del riquadro video. */}
      <div className="player-panel player-in pointer-events-auto relative border border-border-strong bg-elevated shadow-[var(--c-shadow-float)]">
        {/* Il video YouTube non sta in una barra orizzontale: riquadro compatto
            ancorato sopra la barra, a destra, con i controlli dell'iframe.
            Condizioni inline (non un boolean precalcolato): TypeScript narra
            `active` e `data` solo dentro la catena di guardie. */}
        {active.kind === "discovery-preview" && status === "playing" && data?.kind === "youtube" && data.youtube_video_id && (
          <div className="absolute bottom-full right-3 mb-2 w-64 max-w-[calc(100vw-2rem)] border border-border-strong bg-elevated shadow-[var(--c-shadow-float)]">
            <div className="aspect-video w-full overflow-hidden">
              <iframe
                data-testid="preview-iframe"
                className="h-full w-full"
                src={`https://www.youtube-nocookie.com/embed/${data.youtube_video_id}?autoplay=1`}
                title={active.item.title}
                allow="autoplay; encrypted-media"
                allowFullScreen
              />
            </div>
          </div>
        )}

        <div className="flex items-center gap-3 px-3 py-2.5 sm:gap-4 sm:px-4 sm:py-3">
          {/* Zona sinistra: cover, titolo/artista, rating. Flessibile (flex-1):
              titolo e artista prendono tutto lo spazio disponibile e troncano
              solo come ultima risorsa. */}
          <div className="flex min-w-0 flex-1 items-center gap-2.5 sm:gap-3">
            {trackHref ? (
              // Secondo bersaglio verso la stessa scheda: fuori dal giro di
              // tabulazione, così la tastiera incontra un solo link.
              <Link href={trackHref} tabIndex={-1} aria-hidden className="shrink-0">
                <TrackCover key={activeKey ?? "x"} track={coverArt} className="h-11 w-11 sm:h-14 sm:w-14" iconSize={18} />
              </Link>
            ) : (
              <TrackCover key={activeKey ?? "x"} track={coverArt} className="h-11 w-11 sm:h-14 sm:w-14" iconSize={18} />
            )}
            <div className="min-w-0">
              {trackHref ? (
                <Link
                  href={trackHref}
                  title={t.player.openTrack}
                  className="block truncate text-sm text-fg-strong underline-offset-[3px] transition-colors hover:underline focus-visible:outline focus-visible:outline-1 focus-visible:outline-fg"
                >
                  {title}
                </Link>
              ) : (
                <div className="truncate text-sm text-fg-strong">{title}</div>
              )}
              <div className="truncate text-xs text-muted">{artist}</div>
            </div>
            {/* Il voto è un'azione da scrivania: sotto sm lo spazio va al
                titolo, che altrimenti si riduce a due lettere. Il selettore si
                apre in fila a destra, dove la zona ha spazio libero: sopra c'è
                il seek sul filetto del pannello. */}
            {active.kind === "local-track" && (
              <span className="hidden shrink-0 sm:inline-flex">
                <RatingDiamond trackId={active.track.id} rating={active.track.rating ?? null} side="right" />
              </span>
            )}
          </div>

          {/* Zona centro: trasporto (o messaggi di stato). Il seek non è più
              qui: vive sul filetto superiore del pannello, quindi al centro
              resta il gruppo compatto dei comandi. YouTube non ha trasporto:
              audio e controlli stanno nell'iframe sopra la barra. */}
          <div className="flex shrink-0 items-center justify-center">
            {active.kind === "local-track" &&
              (localError ? (
                <div className="text-xs text-muted">{t.player.unsupportedFormat}</div>
              ) : (
                <PlayerTransport
                  key={activeKey ?? "x"}
                  src={trackAudioUrl(active.track.id)}
                  testId="local-audio"
                  onAudible={setAudible}
                  onEnded={() => {
                    if (hasNext) next();
                  }}
                  onError={() => {
                    setLocalError(true);
                    setAudible(false);
                  }}
                  prevNext={prevNext}
                  mediaMeta={mediaMeta}
                />
              ))}
            {active.kind === "discovery-preview" && (
              <>
                {status === "loading" && <div className="text-xs text-muted">{t.discovery.previewLoading}</div>}
                {status === "unavailable" && <div className="text-xs text-muted">{t.discovery.noPreview}</div>}
                {status === "playing" && data?.kind === "itunes" && data.audio_url && (
                  <PlayerTransport
                    key={activeKey ?? "x"}
                    src={data.audio_url}
                    testId="preview-audio"
                    onAudible={setAudible}
                    mediaMeta={mediaMeta}
                  />
                )}
              </>
            )}
          </div>

          {/* Zona destra: dati da DJ, ADD per i lead discovery, chiudi. Da sm in
              su prende la stessa larghezza flessibile della zona sinistra, così
              il trasporto resta otticamente al centro della barra; sotto sm
              resta alla sua misura e lo spazio va tutto al titolo. */}
          <div className="flex shrink-0 items-center justify-end gap-2 sm:min-w-0 sm:flex-1">
            {/* I dati della traccia in ascolto: tre celle label/valore divise da
                filetti, la stessa grammatica delle Figure. `mx-auto`: i margini
                automatici si spartiscono lo spazio libero della zona, quindi il
                blocco si centra fra il trasporto e i comandi di chiusura invece
                di appoggiarsi all'uno o agli altri. Da md in su: sotto, lo
                spazio è del titolo. */}
            {active.kind === "local-track" && meta && (meta.bpm != null || meta.camelot || meta.genre) && (
              <span className="mx-auto hidden min-w-0 shrink divide-x divide-border md:flex">
                {meta.bpm != null && (
                  <span className="flex shrink-0 flex-col px-3 first:pl-0">
                    <span className="text-[9px] uppercase tracking-wider text-faint">{t.player.metaBpm}</span>
                    <span className="tnum text-xs text-fg">{meta.bpm % 1 === 0 ? meta.bpm : meta.bpm.toFixed(1)}</span>
                  </span>
                )}
                {meta.camelot && (
                  <span className="flex shrink-0 flex-col px-3 first:pl-0">
                    <span className="text-[9px] uppercase tracking-wider text-faint">{t.player.metaKey}</span>
                    <KeyBadge camelot={meta.camelot} className="text-xs" />
                  </span>
                )}
                {meta.genre && (
                  <span className="flex min-w-0 flex-col px-3 first:pl-0">
                    <span className="text-[9px] uppercase tracking-wider text-faint">{t.player.metaGenre}</span>
                    <span className="max-w-32 truncate text-xs text-fg" title={meta.genre}>{meta.genre}</span>
                  </span>
                )}
              </span>
            )}
            {addInput && (
              <button
                type="button"
                onClick={onAdd}
                disabled={savingAdd || isAdded}
                aria-label={t.discovery.add}
                className="flex items-center gap-1 border border-border-strong px-2 py-1 text-[10px] uppercase tracking-wider text-muted transition-colors hover:bg-surface-2 hover:text-fg-strong focus-visible:outline focus-visible:outline-1 focus-visible:outline-fg disabled:opacity-60"
              >
                {isAdded ? <Check size={13} /> : <Plus size={12} />}
                <span className="hidden sm:inline">{t.discovery.add}</span>
              </button>
            )}
            <button
              aria-label={t.player.close}
              onClick={stop}
              className="p-1.5 text-muted transition-colors hover:text-fg-strong focus-visible:outline focus-visible:outline-1 focus-visible:outline-fg"
            >
              <X size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
