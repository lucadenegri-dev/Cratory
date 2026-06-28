"use client";

import { useState } from "react";
import { ExternalLink, Plus, Check, Compass, Music2 } from "lucide-react";
import {
  addDiscoveredTrackToPlaylist,
  fmtDuration,
  type DiscoveryResponse,
  type DiscoveryCandidate,
} from "@/lib/api";
import { Card, Badge, Button, EmptyState, Spinner } from "@/components/ui";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

const SOURCE_LABEL: Record<DiscoveryCandidate["source"], string> = {
  similar_artist: "artista affine",
  similar_track: "traccia affine",
  tag: "genere",
  label: "etichetta",
};

export function ExpandResults({ result, playlistId }: { result: DiscoveryResponse; playlistId: number }) {
  if (result.candidates.length === 0) {
    return (
      <EmptyState icon={<Compass size={28} />} title="Nessun suggerimento">
        La fonte di similarità non ha restituito tracce nuove per questa playlist.
      </EmptyState>
    );
  }
  return (
    <div>
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">
        {result.candidates.length} suggerimenti · {result.scope}
      </h2>
      <div className="grid gap-2">
        {result.candidates.map((c, i) => (
          <CandidateRow key={`${c.artist}-${c.title}-${i}`} c={c} playlistId={playlistId} />
        ))}
      </div>
    </div>
  );
}

function CandidateRow({ c, playlistId }: { c: DiscoveryCandidate; playlistId: number }) {
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const [onSpotify, setOnSpotify] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const add = async () => {
    setAdding(true);
    setAddError(null);
    try {
      const res = await addDiscoveredTrackToPlaylist(playlistId, c);
      setAdded(true);
      setOnSpotify(res.spotify_added);
    } catch (e) {
      setAddError(err(e));
    } finally {
      setAdding(false);
    }
  };

  return (
    <Card className="flex items-center gap-3 p-3">
      {c.album_art_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={c.album_art_url} alt="" className="h-12 w-12 shrink-0 rounded-none object-cover" />
      ) : (
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-none bg-elevated text-faint">
          <Music2 size={18} />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{c.artist} — {c.title}</span>
          {c.label_owned && c.label && <Badge tone="neutral">↳ {c.label}</Badge>}
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-faint">
          <span>{SOURCE_LABEL[c.source]}</span>
          {c.seed && c.source !== "label" && <span className="truncate">· da {c.seed}</span>}
          {c.duration_seconds != null && <span>· {fmtDuration(c.duration_seconds)}</span>}
          {added && onSpotify && <span>· anche su Spotify</span>}
        </div>
        {c.explanation && <p className="mt-1 text-xs text-muted">{c.explanation}</p>}
        {addError && <p className="mt-1 text-xs text-danger">⚠ {addError}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {c.spotify_url && (
          <a
            href={c.spotify_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 rounded-none border border-border-strong px-2.5 py-1.5 text-xs font-medium text-fg transition-colors hover:bg-elevated"
          >
            <ExternalLink size={13} /> Spotify
          </a>
        )}
        <Button size="sm" variant={added ? "ghost" : "outline"} onClick={add} disabled={adding || added}>
          {added ? <><Check size={14} /> Aggiunto</> : adding ? <Spinner /> : <><Plus size={14} /> Aggiungi</>}
        </Button>
      </div>
    </Card>
  );
}
