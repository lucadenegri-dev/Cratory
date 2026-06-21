"use client";

import { useEffect, useState } from "react";
import { Compass, ExternalLink, Music2, Wand2, Plus, Check } from "lucide-react";
import {
  discoveryStatus,
  discoverExpand,
  discoveryAddToLibrary,
  listImportedPlaylists,
  fmtDuration,
  type DiscoveryStatus,
  type DiscoveryResponse,
  type DiscoveryCandidate,
  type Playlist,
} from "@/lib/api";
import { Card, Badge, Alert, Button, EmptyState, Spinner, Select, Field, Checkbox } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

const SOURCE_LABEL: Record<DiscoveryCandidate["source"], string> = {
  similar_artist: "artista affine",
  similar_track: "traccia affine",
  tag: "genere",
};

export default function DiscoveryPage() {
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);
  const [playlistId, setPlaylistId] = useState<number | null>(null);
  const [useAi, setUseAi] = useState(true);
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

  const noPlaylists = playlists != null && playlists.length === 0;

  const marginalia = status?.configured && !noPlaylists ? (
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
        label={status.ai_explanations ? "Spiega con l'AI" : "Spiegazioni AI (configura AI_API_KEY)"}
        checked={aiEnabled}
        onChange={setUseAi}
        disabled={busy || !status.ai_explanations}
      />
      <p className="border-t border-border pt-4 text-xs leading-relaxed text-muted">
        Le tracce affini arrivano da fonti di similarità e sono ordinate per compatibilità tecnica con la playlist.
      </p>
    </div>
  ) : undefined;

  return (
    <PageLayout title="Discovery" marginaliaTitle="Parametri" marginalia={marginalia}>
      <p className="mb-6 text-sm text-muted">Espandi le tue playlist con musica nuova e compatibile.</p>

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
    </PageLayout>
  );
}

function Results({ result }: { result: DiscoveryResponse }) {
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
          <Badge tone="neutral">{c.compatibility}% compat</Badge>
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
