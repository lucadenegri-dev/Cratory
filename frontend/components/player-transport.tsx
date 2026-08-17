"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";

import { useT } from "@/lib/i18n";
import { attachAnalyser, primeOnFirstGesture } from "@/lib/audio-analyser";

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
  // Sblocca il contesto Web Audio al primo gesto utile: l'innesto sull'elemento
  // avviene solo a contesto già in esecuzione, quindi senza questo la prima
  // traccia della sessione non verrebbe mai analizzata. Idempotente.
  useEffect(() => { primeOnFirstGesture(); }, []);
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
  const pct = seekable ? Math.min(100, Math.max(0, (position / duration) * 100)) : 0;

  const toggle = () => {
    const el = audioRef.current;
    if (!el) return;
    if (paused) void el.play();
    else el.pause();
  };

  return (
    <>
      {/* La timeline non vive nella riga: e' il filetto superiore del pannello.
          Assoluta e centrata sul bordo (l'unico antenato posizionato e'
          .player-panel), cosi' il seek prende tutta la larghezza della barra e
          il progresso si legge da qualunque punto. Il vestito sta in
          globals.css (.seek); qui resta un range nativo, con tastiera e
          semantica intatte. */}
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
        style={{ "--p": `${pct}%` } as CSSProperties}
        className="seek absolute inset-x-0 top-0 -translate-y-1/2"
      />
      <div className="flex items-center gap-2.5 sm:gap-3">
        {prevNext && (
          <button
            type="button"
            aria-label={t.player.previous}
            disabled={!prevNext.hasPrev}
            onClick={prevNext.onPrev}
            className="shrink-0 p-1 text-muted transition-colors hover:text-fg-strong focus-visible:outline focus-visible:outline-1 focus-visible:outline-fg disabled:opacity-40 disabled:hover:text-muted"
          >
            <SkipBack size={15} />
          </button>
        )}
        {/* Play/pausa e' l'azione primaria della barra: prende il peso di un
            bottone quadrato bordato, prev/next restano glifi nudi. */}
        <button
          type="button"
          aria-label={paused ? t.player.play : t.player.pause}
          onClick={toggle}
          className="grid h-8 w-8 shrink-0 place-items-center border border-border-strong text-fg-strong transition-colors hover:bg-elevated focus-visible:outline focus-visible:outline-1 focus-visible:outline-fg"
        >
          {paused ? <Play size={16} /> : <Pause size={16} />}
        </button>
        {prevNext && (
          <button
            type="button"
            aria-label={t.player.next}
            disabled={!prevNext.hasNext}
            onClick={prevNext.onNext}
            className="shrink-0 p-1 text-muted transition-colors hover:text-fg-strong focus-visible:outline focus-visible:outline-1 focus-visible:outline-fg disabled:opacity-40 disabled:hover:text-muted"
          >
            <SkipForward size={15} />
          </button>
        )}
        {/* Tempi appaiati come in un indice: trascorso in ink, totale in muted. */}
        <span className="tnum hidden shrink-0 text-[11px] text-muted sm:inline">
          <span className="text-fg">{fmtTime(position)}</span>
          {" / "}
          <span>{seekable ? fmtTime(duration) : "–:––"}</span>
        </span>
      </div>
      <audio
        ref={audioRef}
        data-testid={testId}
        src={src}
        autoPlay
        onPlay={(e) => {
          setPaused(false);
          onAudible(true);
          // Innesto (una volta per elemento) nel grafo Web Audio che alimenta
          // la cabina della Home. Non può azzittire nulla: tocca l'elemento
          // solo a contesto già sbloccato, vedi lib/audio-analyser.ts.
          attachAnalyser(e.currentTarget);
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
    </>
  );
}
