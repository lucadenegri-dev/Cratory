"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { apiGet, trackLabel, type Track, type TransitionCandidate } from "@/lib/api";
import { Card, Input, Badge } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { TrackCover } from "@/components/track-cover";
import { cn } from "@/lib/cn";

const LENSES = [
  { value: "all", label: "Tutte" },
  { value: "technically_safe", label: "Sicure" },
  { value: "good_reset", label: "Reset" },
  { value: "creative_risk", label: "Azzardi" },
] as const;
type Lens = (typeof LENSES)[number]["value"];

export default function TransitionFinder() {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Track[]>([]);
  const [selected, setSelected] = useState<Track | null>(null);
  const [direction, setDirection] = useState<"after" | "before">("after");
  const [lens, setLens] = useState<Lens>("all");
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
    apiGet<TransitionCandidate[]>(`/api/transitions/${direction}/${selected.id}`, {
      limit: 25,
      ...(lens !== "all" ? { lens } : {}),
    }).then(setResults).catch(() => setResults([]));
  }, [selected, direction, lens]);

  const marginalia = (
    <div className="space-y-3 text-xs leading-relaxed text-muted">
      <div>
        <p className="mb-1 font-semibold uppercase tracking-wide text-fg">Score 0–100</p>
        <p>Compatibilità tecnica: BPM (max 50) + tonalità (40) + durata (10). L&apos;energia non entra nello score.</p>
      </div>
      <div>
        <p className="mb-1 font-semibold uppercase tracking-wide text-fg">Classi</p>
        <p><span className="text-fg">Sicura</span>: BPM e chiave compatibili.</p>
        <p><span className="text-fg">Reset voluto</span>: stacco netto (calo di energia o cambio di genere).</p>
        <p><span className="text-fg">Azzardo</span>: BPM o tonalità in contrasto, da gestire.</p>
      </div>
      <p className="text-faint">Score e classi sono deterministici, mai inventati.</p>
    </div>
  );

  return (
    <PageLayout title="Transizioni" marginaliaTitle="Legenda" marginalia={marginalia}>
      <p className="mb-6 text-sm text-muted">Scegli una traccia e scopri cosa ci sta bene prima o dopo, con uno score tecnico.</p>

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
                      <span className="tnum ml-auto shrink-0 text-xs text-faint">{t.bpm?.toFixed(0)} · {t.camelot_key ?? "?"}</span>
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
            <div className="flex items-center gap-2.5 rounded-none border border-border bg-surface px-3 py-2">
              <TrackCover track={selected} className="h-8 w-8" iconSize={14} />
              <span className="text-sm font-medium">{trackLabel(selected)}</span>
              <span className="tnum text-xs text-faint">{selected.bpm?.toFixed(0)} · {selected.camelot_key ?? "?"}</span>
              <button onClick={() => setSelected(null)} className="ml-1 text-faint hover:text-fg"><X size={15} /></button>
            </div>
            <div className="ml-auto inline-flex overflow-hidden rounded-none border border-border-strong text-sm">
              {(["after", "before"] as const).map((d) => (
                <button key={d} onClick={() => setDirection(d)} className={cn("px-3 py-1.5", direction === d ? "bg-fg-strong text-bg font-medium" : "text-muted hover:bg-elevated")}>
                  {d === "after" ? "Dopo" : "Prima"}
                </button>
              ))}
            </div>
          </div>

          <div className="mb-4 flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-wide text-muted">Lente</span>
            {LENSES.map((l) => (
              <button
                key={l.value}
                type="button"
                aria-pressed={lens === l.value}
                onClick={() => setLens(l.value)}
                className={cn(
                  "rounded-none border px-3 py-1 text-xs font-medium transition-colors",
                  lens === l.value
                    ? "border-border-strong bg-elevated text-fg"
                    : "border-border bg-surface text-muted hover:border-border-strong hover:text-fg",
                )}
              >
                {l.label}
              </button>
            ))}
          </div>

          <div className="overflow-hidden border border-border">
            {results.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-muted">
                Nessuna transizione {lens !== "all" ? "di questa classe" : ""} per questa traccia.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {results.map(({ track, score }) => (
                  <li key={track.id} className="px-4 py-3 text-sm">
                    <div className="flex items-center gap-3">
                      <Badge tone="neutral" className="tnum w-9 justify-center">{score.score}</Badge>
                      <Link href={`/tracks/${track.id}`} className="min-w-0 flex-1 truncate font-medium hover:text-fg-strong">{trackLabel(track)}</Link>
                      {track.has_local_file && <Badge tone="success" className="shrink-0">FILE</Badge>}
                      {score.classification && (
                        <Badge tone="neutral" className="shrink-0">
                          <span title={score.classification_reason ?? undefined}>{score.classification_label ?? score.classification}</span>
                        </Badge>
                      )}
                      <span className="tnum shrink-0 text-xs text-muted">{track.bpm?.toFixed(0)} BPM · {track.camelot_key ?? "?"}</span>
                    </div>
                    <p className="mt-1 pl-12 text-xs text-muted">{score.technical_reasons.join(" · ")}</p>
                    {score.warnings.length > 0 && <p className="pl-12 text-xs text-danger">{score.warnings.join(" · ")}</p>}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </>
      )}
    </PageLayout>
  );
}
