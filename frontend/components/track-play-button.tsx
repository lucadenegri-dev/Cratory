"use client";

import { Pause, Play } from "lucide-react";

import { useT } from "@/lib/i18n";
import { usePlayer } from "@/lib/player";

type Props = {
  track: { id: number; title: string | null; artist: string | null; has_local_file?: boolean | null };
  className?: string;
};

/** Play/pausa dell'audizione rapida di una traccia posseduta. Non renderizza
 *  nulla se la traccia non ha un file locale. Riusabile in ogni riga-traccia. */
export function TrackPlayButton({ track, className }: Props) {
  const player = usePlayer();
  const t = useT();
  if (!track.has_local_file) return null;

  const isActive = player.active?.kind === "local-track" && player.active.track.id === track.id;

  const toggle = (e: React.MouseEvent) => {
    e.stopPropagation(); // non attivare la navigazione della riga
    if (isActive) {
      player.stop();
    } else {
      player.play({
        kind: "local-track",
        track: { id: track.id, title: track.title ?? "", artist: track.artist ?? "" },
      });
    }
  };

  return (
    <button
      type="button"
      aria-label={isActive ? t.player.stop : t.player.play}
      onClick={toggle}
      className={className ?? "shrink-0 text-faint transition-colors hover:text-fg"}
    >
      {isActive ? <Pause size={14} /> : <Play size={14} />}
    </button>
  );
}
