"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import {
  apiGet, fmtDuration, trackLabel,
  type TrackDetail, type TransitionCandidate,
} from "@/lib/api";

function TransitionList({ title, items }: { title: string; items: TransitionCandidate[] }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <h3 className="mb-2 font-semibold">{title}</h3>
      <ul className="space-y-2">
        {items.map(({ track, score }) => (
          <li key={track.id} className="text-sm">
            <div className="flex items-center gap-2">
              <span className={`w-8 shrink-0 rounded px-1 text-center text-xs font-bold ${
                score.score >= 70 ? "bg-emerald-900 text-emerald-300"
                : score.score >= 45 ? "bg-amber-900 text-amber-300"
                : "bg-red-950 text-red-300"}`}>
                {score.score}
              </span>
              <Link href={`/tracks/${track.id}`} className="truncate text-emerald-400 hover:underline">
                {trackLabel(track)}
              </Link>
              <span className="shrink-0 text-xs text-zinc-500">
                {track.bpm?.toFixed(0)} BPM · {track.tonality ?? "?"}
              </span>
            </div>
            {score.warnings.length > 0 && (
              <p className="ml-10 text-xs text-amber-500">{score.warnings.join("; ")}</p>
            )}
          </li>
        ))}
      </ul>
    </div>
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

  if (error) return <p className="rounded bg-red-950 p-3 text-sm text-red-300">⚠ {error}</p>;
  if (!track) return <p className="text-zinc-400">Caricamento…</p>;

  const rows: [string, React.ReactNode][] = [
    ["Artista", track.artist ?? "—"],
    ["Album", track.album ?? "—"],
    ["Genere", track.genre ?? "—"],
    ["Anno", track.year ?? "—"],
    ["BPM", track.bpm?.toFixed(2) ?? "—"],
    ["Tonalità", track.tonality ?? "—"],
    ["Durata", fmtDuration(track.duration_seconds)],
    ["Sorgente", track.source_type],
    ["Play count", track.play_count],
    ["Beatgrid", track.has_beatgrid ? `sì (${track.beatgrid_bpms.map((b) => b.toFixed(1)).join(", ")} BPM)` : "no"],
  ];

  return (
    <div className="max-w-5xl">
      <h2 className="mb-1 text-2xl font-bold">
        {track.title ?? <span className="italic text-zinc-500">Senza titolo</span>}
      </h2>
      <p className="mb-4 text-zinc-400">{track.artist ?? "Artista sconosciuto"}</p>

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          <table className="w-full text-sm">
            <tbody>
              {rows.map(([k, v]) => (
                <tr key={k} className="border-b border-zinc-800/50 last:border-0">
                  <td className="py-1.5 pr-4 text-zinc-400">{k}</td>
                  <td>{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {track.spotify_url && (
            <a href={track.spotify_url} target="_blank" rel="noreferrer"
              className="mt-3 inline-block rounded bg-green-700 px-3 py-1.5 text-sm hover:bg-green-600">
              Apri su Spotify ↗
            </a>
          )}
        </div>

        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          <h3 className="mb-2 font-semibold">Cue point ({track.cue_points.length})</h3>
          {track.cue_points.length === 0 && <p className="text-sm text-zinc-500">Nessun cue point.</p>}
          <ul className="space-y-1 text-sm">
            {track.cue_points.map((c, i) => (
              <li key={i} className="flex gap-3">
                <span className="w-14 text-zinc-400">{fmtDuration(Math.round(c.start_seconds))}</span>
                <span>{c.name ?? `Cue ${i + 1}`}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 text-xs text-zinc-600">
            “Expand from this track” arriverà con MVP 4 (Library Expansion).
          </p>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <TransitionList title="⬅ Cosa mettere prima" items={before} />
        <TransitionList title="➡ Cosa mettere dopo" items={after} />
      </div>
    </div>
  );
}
