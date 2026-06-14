"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ArrowLeft, ExternalLink, Music4, ArrowRightLeft } from "lucide-react";
import { apiGet, fmtDuration, trackLabel, type TrackDetail, type TransitionCandidate } from "@/lib/api";
import { Card, CardHeader, Badge, Alert, Button } from "@/components/ui";

function scoreTone(s: number) { return s >= 70 ? "success" : s >= 45 ? "warning" : "danger"; }

function TransitionList({ title, items }: { title: string; items: TransitionCandidate[] }) {
  return (
    <Card>
      <CardHeader title={title} />
      <ul className="divide-y divide-border">
        {items.map(({ track, score }) => (
          <li key={track.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
            <Badge tone={scoreTone(score.score)} className="tnum w-9 justify-center">{score.score}</Badge>
            <Link href={`/tracks/${track.id}`} className="min-w-0 flex-1 truncate hover:text-primary">{trackLabel(track)}</Link>
            <span className="tnum shrink-0 text-xs text-faint">{track.bpm?.toFixed(0)} · {track.camelot_key ?? "?"}</span>
          </li>
        ))}
        {items.length === 0 && <li className="px-4 py-6 text-center text-sm text-faint">Nessuna traccia.</li>}
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

  useEffect(() => {
    apiGet<TrackDetail>(`/api/tracks/${id}`).then(setTrack).catch((e) => setError(String(e.message ?? e)));
    apiGet<TransitionCandidate[]>(`/api/transitions/after/${id}`, { limit: 8 }).then(setAfter).catch(() => {});
    apiGet<TransitionCandidate[]>(`/api/transitions/before/${id}`, { limit: 8 }).then(setBefore).catch(() => {});
  }, [id]);

  if (error) return <Alert tone="danger">⚠ {error}</Alert>;
  if (!track) return <p className="text-muted">Caricamento…</p>;

  const rows: Array<[string, React.ReactNode]> = [
    ["Album", track.album ?? "—"], ["Genere", track.genre ?? "—"], ["Anno", track.year ?? "—"],
    ["BPM", track.bpm?.toFixed(2) ?? "—"], ["Key (Camelot)", track.camelot_key ?? "—"], ["Durata", fmtDuration(track.duration_seconds)],
    ["Mood", track.mood ?? "—"], ["Energia", track.energy ?? "—"], ["Label", track.label ?? "—"],
    ["Sorgente", track.source_type], ["ISRC", track.isrc ?? "—"], ["Stato", track.status],
  ];

  return (
    <div>
      <Link href="/library" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Libreria</Link>

      <div className="mb-6 flex items-center gap-4">
        {track.album_art_url
          ? <img src={track.album_art_url} alt="" className="h-20 w-20 rounded-xl object-cover" />
          : <span className="grid h-20 w-20 place-items-center rounded-xl bg-surface-2 text-faint"><Music4 size={28} /></span>}
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

      <h2 className="mb-3 mt-8 flex items-center gap-2 text-lg font-semibold tracking-tight"><ArrowRightLeft size={18} className="text-primary" /> Transizioni</h2>
      <div className="grid gap-4 lg:grid-cols-2">
        <TransitionList title="Cosa mettere prima" items={before} />
        <TransitionList title="Cosa mettere dopo" items={after} />
      </div>
    </div>
  );
}
