"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Plus, X } from "lucide-react";

import { discoverySaveForLater, trackAudioUrl } from "@/lib/api";
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

  return (
    // `bottom` dinamico: se la barra job globale è visibile pubblica la sua
    // altezza in `--jobs-bar-height`, così la barra player le sta sopra invece
    // di sovrapporsi; senza barra job il fallback 0px la tiene sul fondo.
    <div
      ref={barRef}
      style={{ bottom: "var(--jobs-bar-height, 0px)" }}
      // Da lg in su la barra parte al bordo destro della nav (180px, la stessa
      // larghezza di lg:grid-cols-[180px_1fr] in editorial-shell): vive nella
      // colonna dei contenuti, non sotto l'indice.
      className="fixed left-0 right-0 z-[60] border-t border-border-strong bg-surface lg:left-[180px]"
    >
      {/* Il video YouTube non sta in una barra orizzontale: riquadro compatto
          ancorato sopra la barra, a destra, con i controlli dell'iframe.
          Condizioni inline (non un boolean precalcolato): TypeScript narra
          `active` e `data` solo dentro la catena di guardie. */}
      {active.kind === "discovery-preview" && status === "playing" && data?.kind === "youtube" && data.youtube_video_id && (
        <div className="absolute bottom-full right-4 mb-2 w-64 max-w-[calc(100vw-2rem)] border border-border-strong bg-surface">
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

      <div className="flex items-center gap-3 px-3 py-2 sm:gap-4 sm:px-4 sm:py-2.5">
        {/* Zona sinistra: cover, titolo/artista, rating. Flessibile (flex-1):
            titolo e artista prendono tutto lo spazio disponibile e troncano
            solo come ultima risorsa. */}
        <div className="flex min-w-0 flex-1 items-center gap-2.5">
          <TrackCover key={activeKey ?? "x"} track={coverArt} className="h-10 w-10 sm:h-14 sm:w-14" iconSize={18} />
          <div className="min-w-0">
            <div className="truncate text-sm text-fg">{title}</div>
            <div className="truncate text-xs text-faint">{artist}</div>
          </div>
          {active.kind === "local-track" && (
            <RatingDiamond trackId={active.track.id} rating={active.track.rating ?? null} />
          )}
        </div>

        {/* Zona centro: trasporto (o messaggi di stato). Larghezza massima
            contenuta: su schermi larghi il binario di seek non diventa
            chilometrico. YouTube non ha trasporto: audio e controlli stanno
            nell'iframe sopra la barra. */}
        <div className="flex min-w-0 flex-1 justify-center">
          <div className="w-full max-w-2xl">
            {active.kind === "local-track" &&
              (localError ? (
                <div className="text-xs text-faint">{t.player.unsupportedFormat}</div>
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
                {status === "loading" && <div className="text-xs text-faint">{t.discovery.previewLoading}</div>}
                {status === "unavailable" && <div className="text-xs text-faint">{t.discovery.noPreview}</div>}
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
        </div>

        {/* Zona destra: ADD per i lead discovery, chiudi. */}
        <div className="flex shrink-0 items-center gap-1">
          {addInput && (
            <button
              type="button"
              onClick={onAdd}
              disabled={savingAdd || isAdded}
              aria-label={t.discovery.add}
              className="flex items-center gap-1 border border-border-strong px-1.5 py-0.5 text-[11px] uppercase tracking-wider text-faint transition-colors hover:text-fg disabled:opacity-60"
            >
              {isAdded ? <Check size={13} /> : <Plus size={12} />}
              <span className="hidden sm:inline">{t.discovery.add}</span>
            </button>
          )}
          <button aria-label={t.player.close} onClick={stop} className="p-1 text-faint hover:text-fg">
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
