"use client";

import { Pause, Play } from "lucide-react";

import { useT } from "@/lib/i18n";
import { usePlayer, type LocalTrack } from "@/lib/player";

type PlayableRow = {
  id: number;
  title: string | null;
  artist: string | null;
  has_local_file?: boolean | null;
  album_art_url?: string | null;
  rating?: number | null;
};

type Props = {
  track: PlayableRow;
  /** Lista ordinata da cui parte l'ascolto (griglia libreria, set): abilita
   *  prev/next e auto-avanzamento nel player. Viene filtrata alle possedute e
   *  passata come snapshot. */
  context?: PlayableRow[];
  className?: string;
};

function toLocal(tr: PlayableRow): LocalTrack {
  return {
    id: tr.id,
    title: tr.title ?? "",
    artist: tr.artist ?? "",
    albumArtUrl: tr.album_art_url ?? null,
    rating: tr.rating ?? null,
  };
}

/** Play/pausa dell'audizione rapida di una traccia posseduta. Non renderizza
 *  nulla se la traccia non ha un file locale. Riusabile in ogni riga-traccia. */
export function TrackPlayButton({ track, context, className }: Props) {
  const player = usePlayer();
  const t = useT();
  if (!track.has_local_file) return null;

  const isActive = player.active?.kind === "local-track" && player.active.track.id === track.id;

  const toggle = (e: React.MouseEvent) => {
    e.stopPropagation(); // non attivare la navigazione della riga
    if (isActive) {
      player.stop();
    } else {
      const ctx = context?.filter((tr) => tr.has_local_file).map(toLocal);
      player.play({ kind: "local-track", track: toLocal(track) }, ctx);
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
