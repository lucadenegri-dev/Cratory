"use client";

import { X } from "lucide-react";

import { useT } from "@/lib/i18n";
import { usePreviewPlayer } from "@/lib/preview-player";

export function DockedPreviewPlayer() {
  const { active, status, data, stop } = usePreviewPlayer();
  const t = useT();
  if (!active || status === "idle") return null;

  return (
    <div className="fixed bottom-4 right-4 z-[60] w-80 max-w-[calc(100vw-2rem)] rounded-none border border-border-strong bg-surface p-3">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm text-fg">{active.title}</div>
          <div className="truncate text-xs text-faint">{active.artist}</div>
        </div>
        <button aria-label={t.discovery.closePreview} onClick={stop} className="shrink-0 text-faint hover:text-fg">
          <X size={16} />
        </button>
      </div>

      {status === "loading" && <div className="py-2 text-xs text-faint">{t.discovery.previewLoading}</div>}

      {status === "unavailable" && (
        <div className="py-2 text-xs text-faint">{t.discovery.noPreview}</div>
      )}

      {status === "playing" && data?.kind === "itunes" && data.audio_url && (
        <audio data-testid="preview-audio" src={data.audio_url} controls autoPlay className="w-full" />
      )}

      {status === "playing" && data?.kind === "youtube" && data.youtube_video_id && (
        <div className="aspect-video w-full overflow-hidden">
          <iframe
            data-testid="preview-iframe"
            className="h-full w-full"
            src={`https://www.youtube-nocookie.com/embed/${data.youtube_video_id}?autoplay=1`}
            title={active.title}
            allow="autoplay; encrypted-media"
            allowFullScreen
          />
        </div>
      )}
    </div>
  );
}
