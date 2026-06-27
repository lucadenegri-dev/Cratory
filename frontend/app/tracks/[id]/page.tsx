"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, Music4, ArrowRightLeft, Pencil, Sparkles } from "lucide-react";
import { apiGet, enrichTrack, fmtDuration, trackLabel, type TrackDetail, type TransitionCandidate } from "@/lib/api";
import { Card, CardHeader, Badge, Alert, Button, Spinner, Equalizer } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { TrackEditModal } from "@/components/track-edit-modal";

function TransitionList({ title, items }: { title: string; items: TransitionCandidate[] }) {
  return (
    <Card>
      <CardHeader title={title} />
      <ul className="divide-y divide-border">
        {items.map(({ track, score }) => (
          <li key={track.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
            <Badge tone="neutral" className="tnum w-9 justify-center">{score.score}</Badge>
            <Link href={`/tracks/${track.id}`} className="min-w-0 flex-1 truncate hover:text-fg-strong">{trackLabel(track)}</Link>
            <span className="tnum shrink-0 text-xs text-faint">{track.bpm?.toFixed(0)} · {track.camelot_key ?? "?"}</span>
          </li>
        ))}
        {items.length === 0 && <li className="px-4 py-6 text-center text-sm text-muted">Nessuna traccia.</li>}
      </ul>
    </Card>
  );
}

export default function TrackPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [track, setTrack] = useState<TrackDetail | null>(null);
  const [after, setAfter] = useState<TransitionCandidate[]>([]);
  const [before, setBefore] = useState<TransitionCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [enriching, setEnriching] = useState(false);
  const [enrichErr, setEnrichErr] = useState<string | null>(null);

  const enrich = async () => {
    setEnriching(true);
    setEnrichErr(null);
    try {
      setTrack(await enrichTrack(Number(id)));
    } catch (e) {
      setEnrichErr(String((e as { message?: string })?.message ?? e));
    } finally {
      setEnriching(false);
    }
  };

  useEffect(() => {
    apiGet<TrackDetail>(`/api/tracks/${id}`).then(setTrack).catch((e) => setError(String(e.message ?? e)));
    apiGet<TransitionCandidate[]>(`/api/transitions/after/${id}`, { limit: 8 }).then(setAfter).catch(() => {});
    apiGet<TransitionCandidate[]>(`/api/transitions/before/${id}`, { limit: 8 }).then(setBefore).catch(() => {});
  }, [id]);

  if (error) return <PageLayout title="Traccia"><Alert tone="danger">⚠ {error}</Alert></PageLayout>;
  if (!track) return <PageLayout title="Traccia"><p className="flex items-center gap-2 text-muted"><Equalizer className="h-3.5 w-3.5" /> Caricamento…</p></PageLayout>;

  const rows: Array<[string, React.ReactNode]> = [
    ["Album", track.album ?? "—"], ["Genere", track.genre ?? "—"], ["Anno", track.year ?? "—"],
    ["BPM", track.bpm?.toFixed(2) ?? "—"], ["Key (Camelot)", track.camelot_key ?? "—"], ["Durata", fmtDuration(track.duration_seconds)],
    ["Mood", track.mood ?? "—"], ["Energia", track.energy ?? "—"], ["Label", track.label ?? "—"],
    ["Sorgente", track.source_type], ["ISRC", track.isrc ?? "—"], ["Stato", track.status],
  ];

  const marginalia = (
    <div className="space-y-4">
      <div className="flex flex-col gap-2">
        <Button size="sm" variant="outline" onClick={enrich} disabled={enriching}>
          {enriching ? <Spinner /> : <Sparkles size={14} />} {enriching ? "Arricchimento…" : "Arricchisci"}
        </Button>
        <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Pencil size={14} /> Modifica valori</Button>
        {enrichErr && <p className="text-xs text-danger">⚠ {enrichErr}</p>}
      </div>
      <div className="space-y-2 border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2"><span className="text-muted">Sorgente</span><span className="text-fg">{track.source_type}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">Stato</span><span className="text-fg">{track.status}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">Label</span><span className="truncate text-fg">{track.label ?? "—"}</span></div>
      </div>
    </div>
  );

  return (
    <PageLayout title="Traccia" meta={track.artist ?? undefined} marginaliaTitle="Enrichment" marginalia={marginalia}>
      <Link href="/library" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Libreria</Link>

      <div className="mb-6 flex items-center gap-4">
        {track.album_art_url
          ? <img src={track.album_art_url} alt="" className="h-20 w-20 rounded-none object-cover" />
          : <span className="grid h-20 w-20 place-items-center rounded-none bg-surface-2 text-faint"><Music4 size={28} /></span>}
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{track.title ?? <span className="italic text-faint">Senza titolo</span>}</h1>
          <p className="text-muted">{track.artist ?? "Artista sconosciuto"}</p>
          {track.spotify_url && (
            <a href={track.spotify_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex"><Button size="sm" variant="outline"><ExternalLink size={14} /> Spotify</Button></a>
          )}
        </div>
      </div>

      <Card>
        <CardHeader title="Metadata" />
        <table className="w-full text-sm">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k} className="border-b border-border/50 last:border-0">
                <td className="px-4 py-2 text-muted">{k}</td>
                <td className="px-4 py-2 tnum text-right">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <h2 className="mb-3 mt-8 flex items-center gap-2 text-lg font-semibold tracking-tight"><ArrowRightLeft size={18} className="text-muted" /> Transizioni</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <TransitionList title="Cosa mettere prima" items={before} />
        <TransitionList title="Cosa mettere dopo" items={after} />
      </div>

      <TrackEditModal
        track={track}
        open={editing}
        onClose={() => setEditing(false)}
        onSaved={(t) => setTrack(t)}
      />
    </PageLayout>
  );
}
