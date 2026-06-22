"use client";

import { useEffect, useState } from "react";
import { Compass, ExternalLink, Music2, Wand2, Plus, Check, Radar, Tags } from "lucide-react";
import {
  discoveryStatus,
  discoverExpand,
  discoverByLabels,
  discoveryAddToLibrary,
  listImportedPlaylists,
  getLabels,
  fmtDuration,
  type DiscoveryStatus,
  type DiscoveryResponse,
  type DiscoveryCandidate,
  type Playlist,
  type LabelStats,
} from "@/lib/api";
import { Card, Badge, Alert, Button, EmptyState, Spinner, Select, Field, Checkbox } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { cn } from "@/lib/cn";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

type Mode = "expand" | "labels";

const SOURCE_LABEL: Record<DiscoveryCandidate["source"], string> = {
  similar_artist: "artista affine",
  similar_track: "traccia affine",
  tag: "genere",
  label: "etichetta",
};

export default function DiscoveryPage() {
  const jobs = useJobs();
  const [mode, setMode] = useState<Mode>("expand");
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);

  // expand
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);
  const [playlistId, setPlaylistId] = useState<number | null>(null);
  const [useAi, setUseAi] = useState(true);

  // radar etichette
  const [labels, setLabels] = useState<LabelStats[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // condivisi
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
    getLabels()
      .then((ls) => {
        setLabels(ls);
        setSelected(new Set(ls.slice(0, 6).map((l) => l.label)));
      })
      .catch(() => setLabels([]));
  }, []);

  const aiEnabled = useAi && !!status?.ai_explanations;

  const switchMode = (m: Mode) => {
    setMode(m);
    setResult(null);
    setError(null);
  };

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

  const runRadar = async () => {
    const sel = [...selected];
    setBusy(true);
    setError(null);
    setResult(null);
    jobs.startClientJob("radar", "Radar etichette");
    try {
      setResult(await discoverByLabels(sel.length ? sel : undefined));
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(false);
      jobs.endClientJob("radar");
    }
  };

  const toggleLabel = (label: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(label)) n.delete(label);
      else n.add(label);
      return n;
    });

  const noPlaylists = playlists != null && playlists.length === 0;
  const noLabels = labels != null && labels.length === 0;
  const expandReady = !!status?.configured && !noPlaylists;
  const radarReady = !!status?.spotify_resolver && !noLabels;

  const marginalia =
    mode === "expand"
      ? expandReady
        ? (
          <div className="space-y-3">
            <Field label="Playlist da espandere">
              <Select value={playlistId ?? ""} onChange={(e) => setPlaylistId(Number(e.target.value))} disabled={busy}>
                {playlists?.map((p) => (
                  <option key={p.id} value={p.id}>{p.name} · {p.track_count} tracce</option>
                ))}
              </Select>
            </Field>
            <Button className="w-full" onClick={runExpand} disabled={busy || playlistId == null}>
              {busy ? <Spinner /> : <Wand2 size={15} />} Scopri tracce affini
            </Button>
            <Checkbox
              label={status?.ai_explanations ? "Spiega con l'AI" : "Spiegazioni AI (configura AI_API_KEY)"}
              checked={aiEnabled}
              onChange={setUseAi}
              disabled={busy || !status?.ai_explanations}
            />
            <p className="border-t border-border pt-4 text-xs leading-relaxed text-muted">
              Tracce di gusto affine da aggiungere alla playlist. La parte tecnica
              (BPM, tonalità, transizioni) la cura il Set Builder.
            </p>
          </div>
        )
        : undefined
      : radarReady
        ? (
          <div className="space-y-3">
            <div className="text-[10px] uppercase tracking-wider text-muted">Etichette nel radar</div>
            <div className="flex flex-wrap gap-1.5">
              {labels?.map((l) => {
                const on = selected.has(l.label);
                return (
                  <button
                    key={l.label}
                    type="button"
                    onClick={() => toggleLabel(l.label)}
                    aria-pressed={on}
                    disabled={busy}
                    className={cn(
                      "rounded-none border px-2.5 py-1 text-xs transition-colors",
                      on
                        ? "border-border-strong bg-elevated text-fg"
                        : "border-border bg-surface text-muted hover:border-border-strong hover:text-fg",
                    )}
                  >
                    {l.label}
                  </button>
                );
              })}
            </div>
            <Button className="w-full" onClick={runRadar} disabled={busy || selected.size === 0}>
              {busy ? <Spinner /> : <Radar size={15} />} Scopri dalle etichette
            </Button>
            <p className="border-t border-border pt-4 text-xs leading-relaxed text-muted">
              Tracce delle tue etichette che non hai ancora, ordinate per affinità
              di gusto. Nessuna percentuale tecnica: quella è del Set Builder.
            </p>
          </div>
        )
        : undefined;

  return (
    <PageLayout title="Discovery" marginaliaTitle="Parametri" marginalia={marginalia}>
      <p className="mb-4 text-sm text-muted">Espandi le tue playlist con musica nuova e affine al tuo gusto.</p>

      {/* Mode toggle */}
      <div className="mb-6 inline-flex rounded-none border border-border bg-surface p-1">
        {([
          ["expand", "Espandi playlist"],
          ["labels", "Radar etichette"],
        ] as const).map(([m, label]) => (
          <button
            key={m}
            type="button"
            onClick={() => switchMode(m)}
            aria-pressed={mode === m}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-none px-3 py-1.5 text-sm font-medium transition-colors",
              mode === m ? "bg-elevated text-fg" : "text-muted hover:text-fg",
            )}
          >
            {m === "expand" ? <Wand2 size={14} /> : <Tags size={14} />} {label}
          </button>
        ))}
      </div>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {/* EXPAND */}
      {mode === "expand" && (
        <>
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
          {expandReady && (
            <>
              {busy && !result && (
                <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> Cerco tracce…</div>
              )}
              {result && <Results result={result} />}
              {!busy && !result && (
                <EmptyState icon={<Compass size={28} />} title="Pronto per il discovery">
                  Scegli una playlist nel pannello a destra e premi “Scopri tracce affini”.
                </EmptyState>
              )}
            </>
          )}
        </>
      )}

      {/* RADAR ETICHETTE */}
      {mode === "labels" && (
        <>
          {status && !status.spotify_resolver && (
            <div className="mb-6">
              <Alert tone="info">
                Il Radar etichette usa Spotify: imposta <code className="font-mono">SPOTIFY_CLIENT_ID</code> e
                <code className="font-mono"> SPOTIFY_CLIENT_SECRET</code> in <span className="font-medium">backend/.env</span>.
              </Alert>
            </div>
          )}
          {status?.spotify_resolver && noLabels && (
            <EmptyState icon={<Tags size={28} />} title="Nessuna etichetta in libreria">
              Recupera prima le etichette dalla sezione Etichette, poi torna qui per il radar.
            </EmptyState>
          )}
          {radarReady && (
            <>
              {busy && !result && (
                <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> Scandaglio le etichette…</div>
              )}
              {result && <Results result={result} />}
              {!busy && !result && (
                <EmptyState icon={<Radar size={28} />} title="Pronto per il radar">
                  Scegli le etichette nel pannello a destra e premi “Scopri dalle etichette”.
                </EmptyState>
              )}
            </>
          )}
        </>
      )}
    </PageLayout>
  );
}

function Results({ result }: { result: DiscoveryResponse }) {
  if (result.candidates.length === 0) {
    return (
      <EmptyState icon={<Compass size={28} />} title="Nessun suggerimento">
        {result.mode === "labels"
          ? "Le etichette selezionate non hanno restituito tracce nuove."
          : "La fonte di similarità non ha restituito tracce nuove per questa playlist."}
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
          {added ? <><Check size={14} /> In libreria</> : adding ? <Spinner /> : <><Plus size={14} /> Aggiungi</>}
        </Button>
      </div>
    </Card>
  );
}
