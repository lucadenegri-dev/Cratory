"use client";

import { useCallback, useEffect, useState } from "react";
import { Compass, Sparkles, ExternalLink, AlertTriangle, Info, Music2, Wand2, Plus, Check } from "lucide-react";
import {
  discoveryStatus,
  discoverExpand,
  discoverGap,
  discoveryAddToLibrary,
  listImportedPlaylists,
  playlistGaps,
  fmtDuration,
  type DiscoveryStatus,
  type DiscoveryResponse,
  type DiscoveryCandidate,
  type Playlist,
  type Gap,
  type GapAnalysis,
} from "@/lib/api";
import { Card, CardHeader, Badge, Alert, Button, EmptyState, Spinner, Select, Field, Checkbox } from "@/components/ui";
import { cn } from "@/lib/cn";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

type Tab = "expand" | "gap";

const SOURCE_LABEL: Record<DiscoveryCandidate["source"], string> = {
  similar_artist: "artista affine",
  similar_track: "traccia affine",
  tag: "genere",
};

export default function DiscoveryPage() {
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);
  const [tab, setTab] = useState<Tab>("expand");
  const [playlistId, setPlaylistId] = useState<number | null>(null);
  const [useAi, setUseAi] = useState(true);
  const [gaps, setGaps] = useState<GapAnalysis | null>(null);
  const [activeGap, setActiveGap] = useState<string | null>(null);
  const [result, setResult] = useState<DiscoveryResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    discoveryStatus().then(setStatus).catch((e) => setError(err(e)));
    listImportedPlaylists()
      .then((pls) => {
        setPlaylists(pls);
        if (pls.length) setPlaylistId(pls[0].id);
      })
      .catch((e) => setError(err(e)));
  }, []);

  const aiEnabled = useAi && !!status?.ai_explanations;

  const loadGaps = useCallback(async (pid: number) => {
    setGaps(null);
    setActiveGap(null);
    try {
      setGaps(await playlistGaps(pid));
    } catch (e) {
      setError(err(e));
    }
  }, []);

  // In modalità gap, carica i buchi della playlist selezionata.
  useEffect(() => {
    if (tab === "gap" && playlistId != null) loadGaps(playlistId);
  }, [tab, playlistId, loadGaps]);

  const runExpand = async () => {
    if (playlistId == null) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await discoverExpand(playlistId, { use_ai: aiEnabled }));
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(false);
    }
  };

  const runGap = async (gap: Gap) => {
    if (playlistId == null) return;
    setBusy(true);
    setError(null);
    setResult(null);
    setActiveGap(gap.gap_type);
    try {
      setResult(await discoverGap(gap, playlistId, { use_ai: aiEnabled }));
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(false);
    }
  };

  const noPlaylists = playlists != null && playlists.length === 0;

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Discovery</h1>
        <p className="mt-1 text-sm text-muted">
          Scopri musica nuova compatibile con le tue playlist. Tracce affini da Last.fm,
          risolte su Spotify e ordinate per compatibilità.
        </p>
      </header>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {status && !status.configured && (
        <div className="mb-6">
          <Alert tone="info">
            Discovery non configurato: imposta <code className="font-mono">LASTFM_API_KEY</code> in
            <span className="font-medium"> backend/.env</span> (chiave gratuita su last.fm/api).
          </Alert>
        </div>
      )}

      {noPlaylists && (
        <EmptyState icon={<Music2 size={28} />} title="Nessuna playlist importata">
          Importa una playlist dalla sezione Playlist per poterla espandere con il Discovery.
        </EmptyState>
      )}

      {status?.configured && !noPlaylists && (
        <>
          {/* Tabs */}
          <div className="mb-4 inline-flex rounded-lg border border-border bg-surface p-1">
            <TabButton active={tab === "expand"} onClick={() => { setTab("expand"); setResult(null); }} icon={<Sparkles size={15} />}>
              Espandi playlist
            </TabButton>
            <TabButton active={tab === "gap"} onClick={() => { setTab("gap"); setResult(null); }} icon={<Compass size={15} />}>
              Colma un buco
            </TabButton>
          </div>

          <Card className="mb-6">
            <div className="grid gap-4 p-4 sm:grid-cols-[1fr_auto] sm:items-end">
              <Field label="Playlist">
                <Select
                  value={playlistId ?? ""}
                  onChange={(e) => setPlaylistId(Number(e.target.value))}
                  disabled={busy}
                >
                  {playlists?.map((p) => (
                    <option key={p.id} value={p.id}>{p.name} · {p.track_count} tracce</option>
                  ))}
                </Select>
              </Field>
              {tab === "expand" && (
                <Button onClick={runExpand} disabled={busy || playlistId == null}>
                  {busy ? <Spinner /> : <Wand2 size={15} />} Scopri tracce affini
                </Button>
              )}
            </div>
            <div className="border-t border-border px-4 py-3">
              <Checkbox
                label={
                  status.ai_explanations
                    ? "Spiega ogni suggerimento con l'AI"
                    : "Spiegazioni AI (configura AI_API_KEY per abilitarle)"
                }
                checked={aiEnabled}
                onChange={setUseAi}
                disabled={busy || !status.ai_explanations}
              />
            </div>
          </Card>

          {/* Gap picker */}
          {tab === "gap" && (
            <Card className="mb-6">
              <CardHeader title="Buchi della playlist" subtitle="Scegli quale problema vuoi colmare" />
              <div className="grid gap-2 p-4">
                {!gaps && <p className="text-sm text-muted"><Spinner /> Analizzo…</p>}
                {gaps && gaps.gaps.length === 0 && (
                  <p className="text-sm text-success">Nessun buco rilevante: la playlist è bilanciata.</p>
                )}
                {gaps?.gaps.map((g) => (
                  <button
                    key={g.gap_type}
                    onClick={() => runGap(g)}
                    disabled={busy}
                    className={cn(
                      "flex items-start gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors disabled:opacity-50",
                      activeGap === g.gap_type ? "border-primary bg-primary/10" : "border-border hover:bg-elevated",
                    )}
                  >
                    {g.severity === "warning"
                      ? <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />
                      : <Info size={15} className="mt-0.5 shrink-0 text-info" />}
                    <span>
                      <span className="text-fg">{g.description}</span>{" "}
                      <span className="text-muted">{g.suggestion}</span>
                    </span>
                  </button>
                ))}
              </div>
            </Card>
          )}

          {/* Results */}
          {busy && !result && (
            <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> Cerco tracce…</div>
          )}
          {result && <Results result={result} />}
        </>
      )}
    </div>
  );
}

function TabButton({ active, onClick, icon, children }: {
  active: boolean; onClick: () => void; icon: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
        active ? "bg-elevated text-fg" : "text-muted hover:text-fg",
      )}
    >
      {icon}{children}
    </button>
  );
}

function Results({ result }: { result: DiscoveryResponse }) {
  if (result.candidates.length === 0) {
    return (
      <EmptyState icon={<Compass size={28} />} title="Nessun suggerimento">
        La fonte di similarità non ha restituito tracce nuove per questo input.
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
          <CandidateRow key={`${c.artist}-${c.title}-${i}`} c={c} />
        ))}
      </div>
    </div>
  );
}

function compatTone(score: number): "success" | "primary" | "neutral" {
  if (score >= 70) return "success";
  if (score >= 45) return "primary";
  return "neutral";
}

function CandidateRow({ c }: { c: DiscoveryCandidate }) {
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const add = async () => {
    setAdding(true);
    setAddError(null);
    try {
      await discoveryAddToLibrary(c);
      setAdded(true);
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
        <img src={c.album_art_url} alt="" className="h-12 w-12 shrink-0 rounded-md object-cover" />
      ) : (
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-md bg-elevated text-faint">
          <Music2 size={18} />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium">{c.artist} — {c.title}</span>
          <Badge tone={compatTone(c.compatibility)}>{c.compatibility}% compat</Badge>
        </div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-faint">
          <span>{SOURCE_LABEL[c.source]}</span>
          {c.seed && <span className="truncate">· da {c.seed}</span>}
          {c.duration_seconds != null && <span>· {fmtDuration(c.duration_seconds)}</span>}
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
            className="inline-flex items-center gap-1 rounded-lg border border-border-strong px-2.5 py-1.5 text-xs font-medium text-fg transition-colors hover:bg-elevated"
          >
            <ExternalLink size={13} /> Spotify
          </a>
        )}
        <Button size="sm" variant={added ? "ghost" : "outline"} onClick={add} disabled={adding || added}>
          {added ? <><Check size={14} /> In libreria</> : adding ? <Spinner /> : <><Plus size={14} /> Aggiungi</>}
        </Button>
      </div>
    </Card>
  );
}
