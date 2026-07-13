"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Search, X } from "lucide-react";
import { errText, transitions as fetchTransitions, apiGet, trackLabel, type Track, type TransitionCandidate } from "@/lib/api";
import { Alert, Card, Input, Badge, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { TrackCover } from "@/components/track-cover";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

const LENS_DEFS = [
  { value: "all", key: "all" },
  { value: "technically_safe", key: "technicallySafe" },
  { value: "good_reset", key: "goodReset" },
  { value: "creative_risk", key: "creativeRisk" },
] as const;
type Lens = (typeof LENS_DEFS)[number]["value"];

export default function TransitionFinder() {
  const t = useT();
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Track[]>([]);
  const [selected, setSelected] = useState<Track | null>(null);
  const [lens, setLens] = useState<Lens>("all");
  // Risposta taggata con la chiave della richiesta che l'ha prodotta: lo stato
  // si aggiorna solo nei callback async (niente setState sincrono nell'effect)
  // e i risultati stantii di una richiesta precedente vengono ignorati.
  const [response, setResponse] = useState<
    { key: string; results: TransitionCandidate[] | null; error: string | null } | null
  >(null);
  const requestKey = selected ? `${selected.id}:${lens}` : null;

  useEffect(() => {
    if (!query) return;
    const ac = new AbortController();
    const timer = setTimeout(() => {
      Promise.all([
        apiGet<{ items: Track[] }>("/api/tracks", { title: query, limit: 8 }, { signal: ac.signal }),
        apiGet<{ items: Track[] }>("/api/tracks", { artist: query, limit: 8 }, { signal: ac.signal }),
      ]).then(([a, b]) => {
        const seen = new Set<number>();
        setMatches([...a.items, ...b.items].filter((tr) => (seen.has(tr.id) ? false : (seen.add(tr.id), true))).slice(0, 10));
      }).catch((e) => { if (e?.name !== "AbortError") setMatches([]); });
    }, 250);
    return () => { clearTimeout(timer); ac.abort(); };
  }, [query]);

  useEffect(() => {
    if (!selected || !requestKey) return;
    const ac = new AbortController();
    fetchTransitions(selected.id, {
      limit: 25,
      ...(lens !== "all" ? { lens } : {}),
      signal: ac.signal,
    })
      .then((data) => setResponse({ key: requestKey, results: data, error: null }))
      .catch((e) => { if (e?.name !== "AbortError") setResponse({ key: requestKey, results: null, error: errText(e) }); });
    return () => ac.abort();
  }, [selected, lens, requestKey]);

  const current = response && response.key === requestKey ? response : null;
  const loading = selected !== null && current === null;
  const results = current?.results ?? null;
  const error = current?.error ?? null;

  const marginalia = (
    <div className="space-y-3 text-xs leading-relaxed text-muted">
      <div>
        <p className="mb-1 font-semibold uppercase tracking-wide text-fg">{t.transitions.scoreHeading}</p>
        <p>{t.transitions.scoreExplanation}</p>
      </div>
      <div>
        <p className="mb-1 font-semibold uppercase tracking-wide text-fg">{t.transitions.classesHeading}</p>
        <p><span className="text-fg">{t.transitions.classSafeLabel}</span>{t.transitions.classSafeDesc}</p>
        <p><span className="text-fg">{t.transitions.classResetLabel}</span>{t.transitions.classResetDesc}</p>
        <p><span className="text-fg">{t.transitions.classRiskLabel}</span>{t.transitions.classRiskDesc}</p>
      </div>
      <p className="text-faint">{t.transitions.deterministicNote}</p>
    </div>
  );

  return (
    <PageLayout title={t.transitions.pageTitle} marginaliaTitle={t.transitions.legendTitle} marginalia={marginalia}>
      <p className="mb-6 text-sm text-muted">{t.transitions.intro}</p>

      {!selected && (
        <div className="relative max-w-lg">
          <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-faint" />
          <Input
            className="pl-9"
            placeholder={t.transitions.searchPlaceholder}
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
                {matches.map((tr) => (
                  <li key={tr.id}>
                    <button onClick={() => { setSelected(tr); setQuery(""); setMatches([]); }} className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-elevated">
                      <span className="truncate">{trackLabel(tr)}</span>
                      <span className="tnum ml-auto shrink-0 text-xs text-faint">{tr.bpm?.toFixed(0)} · {tr.camelot_key ?? "?"}</span>
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
          </div>

          <div className="mb-4 flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase tracking-wide text-muted">{t.transitions.lensLabel}</span>
            {LENS_DEFS.map((l) => (
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
                {t.transitions.lenses[l.key]}
              </button>
            ))}
          </div>

          {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

          {loading && <Loading label={t.transitions.loadingResults} />}

          {!loading && !error && results && (
          <div className="overflow-hidden border border-border">
            {results.length === 0 ? (
              <p className="px-4 py-8 text-center text-sm text-muted">
                {t.transitions.noResultsMessage(lens !== "all")}
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {results.map(({ track, score }) => (
                  <li key={track.id} className="px-4 py-3 text-sm">
                    <div className="flex items-center gap-3">
                      <Badge tone="neutral" className="tnum w-9 justify-center">{score.score}</Badge>
                      <Link href={`/tracks/${track.id}`} className="min-w-0 flex-1 truncate font-medium hover:text-fg-strong">{trackLabel(track)}</Link>
                      {track.has_local_file && <Badge tone="success" className="shrink-0">{t.transitions.hasFileBadge}</Badge>}
                      {score.classification && (
                        <Badge tone="neutral" className="shrink-0">
                          <span title={score.classification_reason ?? undefined}>
                            {t.transitionLabels[score.classification as keyof typeof t.transitionLabels] ?? score.classification}
                          </span>
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
          )}
        </>
      )}
    </PageLayout>
  );
}
