"use client";

import Link from "next/link";
import { Pencil } from "lucide-react";
import { type Track } from "@/lib/api";
import { withFrom } from "@/lib/back-link";
import { TrackCover } from "@/components/track-cover";
import { TrackPlayButton } from "@/components/track-play-button";
import { useT } from "@/lib/i18n";

/** Vista a griglia della libreria: card cover-centriche sul modello dei
 *  risultati Discovery (DiscoveryLeadGrid). Presentazione pura: riceve tracce
 *  gia' filtrate/paginate, non fa fetch. */
export function LibraryTrackGrid({
  tracks,
  onEdit,
  trackLinkFrom = "",
}: {
  tracks: Track[];
  onEdit: (t: Track) => void;
  /** Origine da passare a `withFrom` per il link verso il dettaglio traccia,
   *  cosi' il back-link li' puo' tornare alla libreria con gli stessi filtri. */
  trackLinkFrom?: string;
}) {
  return (
    <div className="grid grid-cols-[repeat(auto-fill,minmax(120px,1fr))] gap-3">
      {tracks.map((tr) => (
        <LibraryTrackCard key={tr.id} track={tr} context={tracks} onEdit={onEdit} trackLinkFrom={trackLinkFrom} />
      ))}
    </div>
  );
}

function LibraryTrackCard({ track, context, onEdit, trackLinkFrom }: { track: Track; context: Track[]; onEdit: (t: Track) => void; trackLinkFrom: string }) {
  const t = useT();
  // Badge BPM·Key: solo i valori presenti, uniti con " · " (es. "128 · 7A").
  const meta = [track.bpm != null ? track.bpm.toFixed(0) : null, track.camelot_key ?? null]
    .filter(Boolean)
    .join(" · ");
  return (
    <div className="group relative flex flex-col gap-1.5 text-left">
      <Link
        href={withFrom(`/tracks?id=${track.id}`, trackLinkFrom)}
        className="relative block aspect-square w-full overflow-hidden border border-border bg-elevated outline-none focus-visible:ring-1 focus-visible:ring-fg"
      >
        <TrackCover track={track} className="h-full w-full" iconSize={22} />
        {meta && (
          <span className="tnum absolute bottom-1 left-1 border border-border-strong bg-bg px-1 text-[9px] uppercase tracking-wide text-muted">
            {meta}
          </span>
        )}
      </Link>
      {/* Play in alto a sinistra sulla cover, fuori dal Link (niente <button>
          dentro <a>): compare su hover, solo per le tracce possedute. */}
      <TrackPlayButton
        track={track}
        context={context}
        className="absolute left-1 top-1 rounded-full bg-black/60 p-1.5 text-white opacity-0 transition hover:bg-black/80 focus-visible:opacity-100 group-hover:opacity-100"
      />
      {/* Pencil fuori dal Link (niente <button> dentro <a>): overlay su hover. */}
      <button
        type="button"
        onClick={() => onEdit(track)}
        title={t.library.editValuesTitle}
        className="absolute right-1 top-1 border border-border-strong bg-bg p-1 text-faint opacity-0 transition-opacity hover:text-fg-strong focus-visible:opacity-100 group-hover:opacity-100"
      >
        <Pencil size={12} />
      </button>
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-fg">
          {track.title ?? <span className="italic text-faint">{t.library.untitledTrack}</span>}
        </div>
        <div className="truncate text-[11px] text-faint">{track.artist ?? "—"}</div>
      </div>
    </div>
  );
}
