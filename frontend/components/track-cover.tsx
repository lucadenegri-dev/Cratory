"use client";

import { useState } from "react";
import { Music4 } from "lucide-react";
import { trackCoverSrc } from "@/lib/api";

/** Cover di una traccia con fallback: Spotify → artwork embedded del file (per le
 *  possedute) → placeholder. Se l'endpoint disco 404 (file senza cover), ripiega
 *  sul placeholder via onError. `className` porta le classi di dimensione (es. "h-8 w-8"). */
export function TrackCover({
  track,
  className,
  iconSize = 14,
}: {
  track: { id: number; album_art_url?: string | null; has_local_file?: boolean | null };
  className: string;
  iconSize?: number;
}) {
  const [failed, setFailed] = useState(false);
  const src = failed ? null : trackCoverSrc(track);
  if (!src) {
    return (
      <span className={`grid shrink-0 place-items-center rounded-none bg-elevated text-faint ${className}`}>
        <Music4 size={iconSize} />
      </span>
    );
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      className={`shrink-0 rounded-none object-cover ${className}`}
    />
  );
}
