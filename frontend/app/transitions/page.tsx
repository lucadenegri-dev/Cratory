"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  apiGet, trackLabel,
  type Track, type TransitionCandidate,
} from "@/lib/api";

export default function TransitionFinder() {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Track[]>([]);
  const [selected, setSelected] = useState<Track | null>(null);
  const [direction, setDirection] = useState<"after" | "before">("after");
  const [results, setResults] = useState<TransitionCandidate[]>([]);

  useEffect(() => {
    if (!query) { setMatches([]); return; }
    const t = setTimeout(() => {
      // cerca sia per titolo che per artista, unendo i risultati
      Promise.all([
        apiGet<{ items: Track[] }>("/api/tracks", { title: query, limit: 10 }),
        apiGet<{ items: Track[] }>("/api/tracks", { artist: query, limit: 10 }),
      ]).then(([byTitle, byArtist]) => {
        const seen = new Set<number>();
        const merged = [...byTitle.items, ...byArtist.items].filter((t) =>
          seen.has(t.id) ? false : (seen.add(t.id), true));
        setMatches(merged.slice(0, 12));
      }).catch(() => setMatches([]));
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    if (!selected) return;
    apiGet<TransitionCandidate[]>(`/api/transitions/${direction}/${selected.id}`, { limit: 25 })
      .then(setResults)
      .catch(() => setResults([]));
  }, [selected, direction]);

  return (
    <div className="max-w-4xl">
      <h2 className="mb-4 text-2xl font-bold">Transition Finder</h2>

      <input
        className="mb-2 w-full max-w-md rounded border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm"
        placeholder="Cerca una traccia per titolo o artista…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />

      {matches.length > 0 && !selected && (
        <ul className="mb-4 max-w-md divide-y divide-zinc-800 rounded border border-zinc-800 bg-zinc-900">
          {matches.map((t) => (
            <li key={t.id}>
              <button onClick={() => { setSelected(t); setQuery(""); setMatches([]); }}
                className="w-full px-3 py-2 text-left text-sm hover:bg-zinc-800">
                {trackLabel(t)} <span className="text-xs text-zinc-500">{t.bpm?.toFixed(0)} BPM · {t.tonality ?? "?"}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {selected && (
        <div className="mt-4">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <span className="rounded bg-zinc-800 px-3 py-1.5 text-sm">
              {trackLabel(selected)} · {selected.bpm?.toFixed(0)} BPM · {selected.tonality ?? "?"}
            </span>
            <button onClick={() => setSelected(null)} className="text-sm text-zinc-400 hover:text-white">✕ cambia</button>
            <div className="ml-auto flex rounded border border-zinc-700 text-sm">
              <button onClick={() => setDirection("after")}
                className={`px-3 py-1.5 ${direction === "after" ? "bg-emerald-700" : "hover:bg-zinc-800"}`}>Dopo</button>
              <button onClick={() => setDirection("before")}
                className={`px-3 py-1.5 ${direction === "before" ? "bg-emerald-700" : "hover:bg-zinc-800"}`}>Prima</button>
            </div>
          </div>

          <ul className="space-y-2">
            {results.map(({ track, score }) => (
              <li key={track.id} className="rounded border border-zinc-800 bg-zinc-900 p-3 text-sm">
                <div className="flex items-center gap-3">
                  <span className={`w-9 shrink-0 rounded px-1 py-0.5 text-center text-xs font-bold ${
                    score.score >= 70 ? "bg-emerald-900 text-emerald-300"
                    : score.score >= 45 ? "bg-amber-900 text-amber-300"
                    : "bg-red-950 text-red-300"}`}>
                    {score.score}
                  </span>
                  <Link href={`/tracks/${track.id}`} className="text-emerald-400 hover:underline">{trackLabel(track)}</Link>
                  <span className="ml-auto shrink-0 text-xs text-zinc-500">
                    {track.bpm?.toFixed(0)} BPM · {track.tonality ?? "?"}
                  </span>
                </div>
                <p className="ml-12 mt-1 text-xs text-zinc-500">{score.technical_reasons.join("; ")}</p>
                {score.warnings.length > 0 && (
                  <p className="ml-12 text-xs text-amber-500">{score.warnings.join("; ")}</p>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
