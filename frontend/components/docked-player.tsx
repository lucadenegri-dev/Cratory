"use client";

import { useState } from "react";
import { X } from "lucide-react";

import { trackAudioUrl } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { usePlayer } from "@/lib/player";

export function DockedPlayer() {
  const { active, status, data, stop } = usePlayer();
  const t = useT();
  // Errore di riproduzione del file locale (formato non supportato dal browser
  // o file sparito): stato locale, si azzera quando cambia la traccia attiva.
  // Niente useEffect: l'azzeramento avviene "durante il render" (pattern
  // React consigliato per derivare stato da un prop che cambia), evitando
  // il render extra/cascata di un setState sincrono dentro un effect.
  const [localError, setLocalError] = useState(false);
  const activeLocalId = active?.kind === "local-track" ? active.track.id : null;
  const [prevLocalId, setPrevLocalId] = useState(activeLocalId);
  if (activeLocalId !== prevLocalId) {
    setPrevLocalId(activeLocalId);
    setLocalError(false);
  }

  if (!active || status === "idle") return null;

  const title = active.kind === "local-track" ? active.track.title : active.item.title;
  const artist = active.kind === "local-track" ? active.track.artist : active.item.artist;

  return (
    <div className="fixed bottom-4 right-4 z-[60] w-80 max-w-[calc(100vw-2rem)] rounded-none border border-border-strong bg-surface p-3">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm text-fg">{title}</div>
          <div className="truncate text-xs text-faint">{artist}</div>
        </div>
        <button aria-label={t.player.close} onClick={stop} className="shrink-0 text-faint hover:text-fg">
          <X size={16} />
        </button>
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
            onError={() => setLocalError(true)}
            className="w-full"
          />
        ))}

      {active.kind === "discovery-preview" && (
        <>
          {status === "loading" && <div className="py-2 text-xs text-faint">{t.discovery.previewLoading}</div>}
          {status === "unavailable" && <div className="py-2 text-xs text-faint">{t.discovery.noPreview}</div>}
          {status === "playing" && data?.kind === "itunes" && data.audio_url && (
            <audio data-testid="preview-audio" src={data.audio_url} controls autoPlay className="w-full" />
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
