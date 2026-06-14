"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Search, X, Music4 } from "lucide-react";
import { apiGet, trackLabel, type Track, type TransitionCandidate } from "@/lib/api";
import { Card, Input, Badge } from "@/components/ui";
import { cn } from "@/lib/cn";

function scoreTone(s: number) { return s >= 70 ? "success" : s >= 45 ? "warning" : "danger"; }

export default function TransitionFinder() {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Track[]>([]);
  const [selected, setSelected] = useState<Track | null>(null);
  const [direction, setDirection] = useState<"after" | "before">("after");
  const [results, setResults] = useState<TransitionCandidate[]>([]);

  useEffect(() => {
    if (!query) return;
    const t = setTimeout(() => {
      Promise.all([
        apiGet<{ items: Track[] }>("/api/tracks", { title: query, limit: 8 }),
        apiGet<{ items: Track[] }>("/api/tracks", { artist: query, limit: 8 }),
      ]).then(([a, b]) => {
        const seen = new Set<number>();
        setMatches([...a.items, ...b.items].filter((t) => (seen.has(t.id) ? false : (seen.add(t.id), true))).slice(0, 10));
      }).catch(() => setMatches([]));
    }, 250);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    if (!selected) return;
    apiGet<TransitionCandidate[]>(`/api/transitions/${direction}/${selected.id}`, { limit: 25 }).then(setResults).catch(() => setResults([]));
  }, [selected, direction]);

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Transition Finder</h1>
        <p className="mt-1 text-sm text-muted">Scegli una traccia e scopri cosa ci sta bene prima o dopo, con uno score tecnico.</p>
      </header>

      {!selected && (
        <div className="relative max-w-lg">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
          <Input
            className="pl-9"
            placeholder="Cerca per titolo o artista…"
            value={query}
            onChange={(e) => {
              const value = e.target.value;
              setQuery(value);
              if (!value) setMatches([]);
            }}
          />
          {matches.length > 0 && (
            <Card className="absolute z-10 mt-1 w-full overflow-hidden">
              <ul className="divide-y divide-border">
                {matches.map((t) => (
                  <li key={t.id}>
                    <button onClick={() => { setSelected(t); setQuery(""); setMatches([]); }} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-elevated">
                      <span className="truncate">{trackLabel(t)}</span>
                      <span className="tnum ml-auto shrink-0 text-xs text-faint">{t.bpm?.toFixed(0)} · {t.tonality ?? "?"}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}

      {selected && (
        <>
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2.5 rounded-lg border border-border bg-surface px-3 py-2">
              {selected.album_art_url
                ? <img src={selected.album_art_url} alt="" className="h-8 w-8 rounded object-cover" />
                : <span className="grid h-8 w-8 place-items-center rounded bg-elevated text-faint"><Music4 size={14} /></span>}
              <span className="text-sm font-medium">{trackLabel(selected)}</span>
              <span className="tnum text-xs text-faint">{selected.bpm?.toFixed(0)} · {selected.tonality ?? "?"}</span>
              <button onClick={() => setSelected(null)} className="ml-1 text-faint hover:text-fg"><X size={15} /></button>
            </div>
            <div className="ml-auto inline-flex overflow-hidden rounded-lg border border-border-strong text-sm">
              {(["after", "before"] as const).map((d) => (
                <button key={d} onClick={() => setDirection(d)} className={cn("px-3 py-1.5", direction === d ? "bg-primary text-primary-fg font-medium" : "text-muted hover:bg-elevated")}>
                  {d === "after" ? "Dopo" : "Prima"}
                </button>
              ))}
            </div>
          </div>

          <Card className="overflow-hidden">
            <ul className="divide-y divide-border">
              {results.map(({ track, score }) => (
                <li key={track.id} className="px-4 py-3 text-sm">
                  <div className="flex items-center gap-3">
                    <Badge tone={scoreTone(score.score)} className="tnum w-9 justify-center">{score.score}</Badge>
                    <Link href={`/tracks/${track.id}`} className="min-w-0 flex-1 truncate font-medium hover:text-primary">{trackLabel(track)}</Link>
                    <span className="tnum shrink-0 text-xs text-faint">{track.bpm?.toFixed(0)} BPM · {track.tonality ?? "?"}</span>
                  </div>
                  <p className="mt-1 pl-12 text-xs text-faint">{score.technical_reasons.join(" · ")}</p>
                  {score.warnings.length > 0 && <p className="pl-12 text-xs text-warning">{score.warnings.join(" · ")}</p>}
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}
