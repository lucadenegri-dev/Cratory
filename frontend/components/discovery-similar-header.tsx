"use client";

import Link from "next/link";
import { ArrowLeft, ExternalLink } from "lucide-react";

import { TrackCover } from "@/components/track-cover";
import { Checkbox } from "@/components/ui";
import { useT, type Dictionary } from "@/lib/i18n";
import type { DiscoverySimilarResponse, SimilarEdge, Track } from "@/lib/api/types";
import { cn } from "@/lib/cn";

function absentLabel(reason: SimilarEdge["absent_reason"], t: Dictionary): string {
  switch (reason) {
    case "no_band": return t.discovery.similarAbsentNoBand;
    case "self_released": return t.discovery.similarAbsentSelfReleased;
    case "no_label": return t.discovery.similarAbsentNoLabel;
    case "no_tag": return t.discovery.similarAbsentNoTag;
    case "no_year": return t.discovery.similarAbsentNoYear;
    case "off": return t.discovery.similarAbsentOff;
    default: return "";
  }
}

function EdgeChip({ label, edge, t }: { label: string; edge?: SimilarEdge; t: Dictionary }) {
  // Arco assente: NON si mostra "0". Zero vuol dire "ho guardato e non c'era
  // niente"; assente vuol dire "non ho potuto guardare", e sono due fatti diversi.
  const absent = !edge || edge.count === null;
  return (
    <span
      title={absent ? absentLabel(edge?.absent_reason ?? null, t) : undefined}
      className={cn(
        "border border-border px-1.5 py-0.5 text-[10px] uppercase tracking-wider",
        absent ? "text-faint line-through" : "text-muted",
      )}
    >
      {label}{absent ? "" : ` ${edge!.count}`}
    </span>
  );
}

export function DiscoverySimilarHeader({
  data, track, stylePeriod, onStylePeriodChange, busy,
}: {
  data: DiscoverySimilarResponse;
  track: Track;
  stylePeriod: boolean;
  onStylePeriodChange: (v: boolean) => void;
  busy: boolean;
}) {
  const t = useT();
  const origin = data.origin;

  return (
    <div className="mb-6 border border-border p-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          {/* `TrackCover` e non un `<img>` a mano: la traccia di partenza è per
              forza posseduta, e senza `album_art_url` la copertina sta dentro al
              file. È anche l'unico componente che ripiega sul segnaposto se
              l'endpoint disco risponde 404. Decorativa: artista e titolo sono
              scritti qui accanto. */}
          <TrackCover track={track} className="h-10 w-10" iconSize={16} />
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-wider text-muted">
              {t.discovery.similarFrom}
            </div>
            <div className="mt-1 truncate text-sm text-fg">
              {track.artist} — {track.title}
            </div>
            {origin && origin.resolution === "release" ? (
              <div className="mt-1 text-xs text-faint" title={t.discovery.similarResolvedRelease}>
                <span className="truncate">{origin.title}</span>
                {origin.label && <span> · {origin.label}</span>}
                {origin.year != null && <span> · {origin.year}</span>}
                {origin.source_url && (
                  <a href={origin.source_url} target="_blank" rel="noreferrer"
                     className="ml-2 inline-flex items-center gap-1 text-fg hover:underline">
                    <ExternalLink size={12} /> Bandcamp
                  </a>
                )}
              </div>
            ) : origin ? (
              <div className="mt-1 text-xs text-faint">{t.discovery.similarArtistOnly}</div>
            ) : null}
            <Link href={`/tracks?id=${track.id}`}
                  className="mt-2 inline-flex items-center gap-1.5 text-xs text-muted hover:text-fg">
              <ArrowLeft size={13} /> {t.discovery.similarBackToTrack}
            </Link>
          </div>
        </div>

        <div className="flex flex-col items-end gap-2">
          <Checkbox
            label={t.discovery.similarStylePeriod}
            checked={stylePeriod}
            onChange={onStylePeriodChange}
            disabled={busy}
          />
          <div className="flex flex-wrap gap-1.5">
            <EdgeChip label={t.discovery.similarEdgeArtist} edge={data.edges.same_artist} t={t} />
            <EdgeChip label={t.discovery.similarEdgeLabel} edge={data.edges.same_label} t={t} />
            <EdgeChip label={t.discovery.similarEdgeStyle} edge={data.edges.same_period_style} t={t} />
          </div>
        </div>
      </div>
    </div>
  );
}
