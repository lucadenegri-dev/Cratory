"use client";

import { useState } from "react";
import { Check, Plus, X } from "lucide-react";

import { discoverySaveForLater, trackAudioUrl } from "@/lib/api";
import { RatingDiamond } from "@/components/rating-diamond";
import { TrackCover } from "@/components/track-cover";
import { useT } from "@/lib/i18n";
import { usePlayer } from "@/lib/player";

export function DockedPlayer() {
  const { active, status, data, stop, setAudible } = usePlayer();
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

  /* Gli eventi dell'elemento audio, riportati al player: sono l'unica fonte
     onesta del "sta suonando" (autoplay bloccato, pausa, fine traccia). */
  const audioEvents = {
    onPlay: () => setAudible(true),
    onPause: () => setAudible(false),
    onEnded: () => setAudible(false),
  };

  if (!active || status === "idle") return null;

  const title = active.kind === "local-track" ? active.track.title : active.item.title;
  const artist = active.kind === "local-track" ? active.track.artist : active.item.artist;

  // Miniatura: per la traccia posseduta l'artwork Spotify o la cover embedded
  // (via TrackCover); per la preview discovery la thumb del lead. `key` sul
  // dock (più sotto) rimonta TrackCover al cambio sorgente, azzerando il suo
  // stato di fallback.
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
    // altezza in `--jobs-bar-height`, così il dock sale sopra di essa invece di
    // sovrapporsi; senza barra il fallback 0px lo lascia a 1rem dal fondo.
    <div
      style={{ bottom: "calc(var(--jobs-bar-height, 0px) + 1rem)" }}
      className="fixed right-4 z-[60] w-80 max-w-[calc(100vw-2rem)] rounded-none border border-border-strong bg-surface p-3"
    >
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <TrackCover key={activeKey ?? "x"} track={coverArt} className="h-10 w-10" iconSize={16} />
          <div className="min-w-0">
            <div className="truncate text-sm text-fg">{title}</div>
            <div className="truncate text-xs text-faint">{artist}</div>
          </div>
        </div>
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
              {t.discovery.add}
            </button>
          )}
          {active.kind === "local-track" && (
            <RatingDiamond trackId={active.track.id} rating={active.track.rating ?? null} />
          )}
          <button aria-label={t.player.close} onClick={stop} className="text-faint hover:text-fg">
            <X size={16} />
          </button>
        </div>
      </div>

      {active.kind === "local-track" &&
        (localError ? (
          <div className="py-2 text-xs text-faint">{t.player.unsupportedFormat}</div>
        ) : (
          <audio
            data-testid="local-audio"
            src={trackAudioUrl(active.track.id)}
            controls
            autoPlay
            {...audioEvents}
            onError={() => { setLocalError(true); setAudible(false); }}
            className="w-full"
          />
        ))}

      {active.kind === "discovery-preview" && (
        <>
          {status === "loading" && <div className="py-2 text-xs text-faint">{t.discovery.previewLoading}</div>}
          {status === "unavailable" && <div className="py-2 text-xs text-faint">{t.discovery.noPreview}</div>}
          {status === "playing" && data?.kind === "itunes" && data.audio_url && (
            <audio data-testid="preview-audio" src={data.audio_url} controls autoPlay {...audioEvents} className="w-full" />
          )}
          {status === "playing" && data?.kind === "youtube" && data.youtube_video_id && (
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
          )}
        </>
      )}
    </div>
  );
}
