"use client";

import { useEffect, useRef, useState } from "react";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";

import { useT } from "@/lib/i18n";

export type TransportPrevNext = {
  hasPrev: boolean;
  hasNext: boolean;
  onPrev: () => void;
  onNext: () => void;
};

type Props = {
  src: string;
  testId: string;
  /** Pubblica gli eventi reali dell'elemento (play/pause/ended): alimenta `audible`. */
  onAudible: (v: boolean) => void;
  onEnded?: () => void;
  onError?: () => void;
  /** Presente solo quando c'è un contesto d'ascolto: mostra prev/next. */
  prevNext?: TransportPrevNext | null;
  /** Metadata per il Now Playing di sistema (Media Session). */
  mediaMeta?: { title: string; artist: string; artworkUrl: string | null } | null;
};

/** mm:ss per il trasporto: a differenza di fmtDuration niente "—", a riposo 0:00. */
function fmtTime(s: number): string {
  if (!Number.isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

/** Trasporto custom sul motore <audio> nascosto: play/pause, prev/next (solo con
 *  contesto), seek con tempi. Riusato identico per traccia locale, clip iTunes e
 *  stream Bandcamp; l'iframe YouTube non passa di qui. */
export function PlayerTransport({ src, testId, onAudible, onEnded, onError, prevNext, mediaMeta }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [paused, setPaused] = useState(true);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const t = useT();

  // Now Playing di sistema: metadata e comandi remoti (tasti multimediali,
  // lock screen). Feature facoltativa: dove mediaSession/MediaMetadata mancano
  // (browser vecchi, jsdom) non succede nulla. prev/next registrati solo con
  // contesto e solo verso i bordi disponibili; allo smontaggio si azzera tutto
  // per non lasciare comandi appesi a un elemento morto.
  useEffect(() => {
    if (!("mediaSession" in navigator) || typeof MediaMetadata === "undefined") return;
    const ms = navigator.mediaSession;
    ms.metadata = new MediaMetadata({
      title: mediaMeta?.title ?? "",
      artist: mediaMeta?.artist ?? "",
      artwork: mediaMeta?.artworkUrl ? [{ src: mediaMeta.artworkUrl }] : [],
    });
    ms.setActionHandler("play", () => void audioRef.current?.play());
    ms.setActionHandler("pause", () => audioRef.current?.pause());
    ms.setActionHandler("previoustrack", prevNext?.hasPrev ? () => prevNext.onPrev() : null);
    ms.setActionHandler("nexttrack", prevNext?.hasNext ? () => prevNext.onNext() : null);
    return () => {
      ms.metadata = null;
      ms.setActionHandler("play", null);
      ms.setActionHandler("pause", null);
      ms.setActionHandler("previoustrack", null);
      ms.setActionHandler("nexttrack", null);
    };
  }, [mediaMeta, prevNext]);

  // Stream senza durata nota (metadata non ancora arrivati, o live): il seek
  // non ha senso e resta disabilitato.
  const seekable = Number.isFinite(duration) && duration > 0;

  const toggle = () => {
    const el = audioRef.current;
    if (!el) return;
    if (paused) void el.play();
    else el.pause();
  };

  return (
    <div className="flex w-full items-center gap-3">
      {prevNext && (
        <button
          type="button"
          aria-label={t.player.previous}
          disabled={!prevNext.hasPrev}
          onClick={prevNext.onPrev}
          className="shrink-0 text-faint transition-colors hover:text-fg disabled:opacity-40 disabled:hover:text-faint"
        >
          <SkipBack size={15} />
        </button>
      )}
      <button
        type="button"
        aria-label={paused ? t.player.play : t.player.pause}
        onClick={toggle}
        className="shrink-0 text-fg transition-colors hover:text-fg-strong"
      >
        {paused ? <Play size={17} /> : <Pause size={17} />}
      </button>
      {prevNext && (
        <button
          type="button"
          aria-label={t.player.next}
          disabled={!prevNext.hasNext}
          onClick={prevNext.onNext}
          className="shrink-0 text-faint transition-colors hover:text-fg disabled:opacity-40 disabled:hover:text-faint"
        >
          <SkipForward size={15} />
        </button>
      )}
      <span className="tnum shrink-0 text-[11px] text-faint">{fmtTime(position)}</span>
      <input
        type="range"
        aria-label={t.player.seek}
        min={0}
        max={seekable ? duration : 0}
        step={0.1}
        value={seekable ? Math.min(position, duration) : 0}
        disabled={!seekable}
        onChange={(e) => {
          const el = audioRef.current;
          if (!el) return;
          const v = Number(e.target.value);
          el.currentTime = v;
          setPosition(v);
        }}
        className="h-1 min-w-0 flex-1 cursor-pointer appearance-none bg-border text-fg accent-current disabled:cursor-default"
      />
      <span className="tnum shrink-0 text-[11px] text-faint">{seekable ? fmtTime(duration) : "–:––"}</span>
      <audio
        ref={audioRef}
        data-testid={testId}
        src={src}
        autoPlay
        onPlay={() => {
          setPaused(false);
          onAudible(true);
        }}
        onPause={() => {
          setPaused(true);
          onAudible(false);
        }}
        onEnded={() => {
          setPaused(true);
          onAudible(false);
          onEnded?.();
        }}
        onError={() => onError?.()}
        onTimeUpdate={(e) => setPosition(e.currentTarget.currentTime)}
        onDurationChange={(e) => setDuration(e.currentTarget.duration)}
        className="hidden"
      />
    </div>
  );
}
