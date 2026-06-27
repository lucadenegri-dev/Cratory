"use client";

import { useEffect, useState } from "react";
import { Compass, ExternalLink, Music2, Wand2, Plus, Check, Disc3, Search, Tags } from "lucide-react";
import {
  discoveryStatus,
  discoverExpand,
  discoveryAddToLibrary,
  discoveryDig,
  discoveryAddLead,
  getDiscoveryGenres,
  listImportedPlaylists,
  getLabels,
  fmtDuration,
  type DiscoveryStatus,
  type DiscoveryResponse,
  type DiscoveryCandidate,
  type DiscoveryDigResponse,
  type DiscoveryLead,
  type DiscoveryGenres,
  type Playlist,
  type LabelStats,
} from "@/lib/api";
import { Card, Badge, Alert, Button, EmptyState, Spinner, Select, Field, Checkbox, Input } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { cn } from "@/lib/cn";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

type Mode = "expand" | "dig";
type DigSeed = "genre" | "label";
const CHIP_CAP = 12;

const SOURCE_LABEL: Record<DiscoveryCandidate["source"], string> = {
  similar_artist: "artista affine",
  similar_track: "traccia affine",
  tag: "genere",
  label: "etichetta",
};

const PRESETS: { key: string; label: string; value: number; desc: string }[] = [
  { key: "familiare", label: "Familiare", value: 0.15, desc: "Artisti e nomi che probabilmente conosci già." },
  { key: "bilanciato", label: "Bilanciato", value: 0.45, desc: "Un mix tra noto e nuovo." },
  { key: "avventuroso", label: "Avventuroso", value: 0.85, desc: "Rarità e deep cut richiesti che non conosci." },
];

export default function DiscoveryPage() {
  const jobs = useJobs();
  const [mode, setMode] = useState<Mode>("dig");
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);

  // espandi playlist
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);
  const [playlistId, setPlaylistId] = useState<number | null>(null);
  const [useAi, setUseAi] = useState(true);

  // scava (dig Discogs)
  const [digSeed, setDigSeed] = useState<DigSeed>("genre");
  const [genres, setGenres] = useState<DiscoveryGenres | null>(null);
  const [genre, setGenre] = useState<string>("");
  const [labels, setLabels] = useState<LabelStats[] | null>(null);
  const [selectedLabel, setSelectedLabel] = useState<string>("");
  const [showAllLabels, setShowAllLabels] = useState(false);
  const [adventurousness, setAdventurousness] = useState(0.45);
  const [dig, setDig] = useState<DiscoveryDigResponse | null>(null);

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
    getDiscoveryGenres()
      .then((g) => {
        setGenres(g);
        setGenre(g.library[0] ?? g.styles[0] ?? "");
      })
      .catch(() => setGenres({ library: [], styles: [] }));
    getLabels()
      .then((ls) => {
        setLabels(ls);
        if (ls.length) setSelectedLabel(ls[0].label);
      })
      .catch(() => setLabels([]));
  }, []);

  const aiEnabled = useAi && !!status?.ai_explanations;

  const switchMode = (m: Mode) => {
    setMode(m);
    setResult(null);
    setDig(null);
    setError(null);
  };

  const switchSeed = (s: DigSeed) => {
    setDigSeed(s);
    setDig(null);
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

  const runDig = async () => {
    const value = digSeed === "genre" ? genre.trim() : selectedLabel;
    if (!value) return;
    setBusy(true);
    setError(null);
    setDig(null);
    jobs.startClientJob("dig", "Crate digging");
    try {
      setDig(await discoveryDig(digSeed, value, { adventurousness }));
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(false);
      jobs.endClientJob("dig");
    }
  };

  const noPlaylists = playlists != null && playlists.length === 0;
  const expandReady = !!status?.configured && !noPlaylists;
  const quickGenres = (genres?.library.length ? genres.library : genres?.styles ?? []).slice(0, 10);
  const visibleLabels =
    labels && !showAllLabels
      ? labels.filter((l, i) => i < CHIP_CAP || l.label === selectedLabel)
      : labels ?? [];
  const hiddenLabelCount = (labels?.length ?? 0) - visibleLabels.length;
  const activePreset = PRESETS.find((p) => p.value === adventurousness) ?? PRESETS[1];
  const noLabels = labels != null && labels.length === 0;
  const digReady = digSeed === "genre" ? !!genre.trim() : !!selectedLabel;

  return (
    <PageLayout title="Discovery">
      <p className="mb-4 text-sm text-muted">Scava nuova musica per genere o etichetta, o espandi una playlist.</p>

      {/* Mode toggle */}
      <div className="mb-4 inline-flex rounded-none border border-border bg-surface p-1">
        {([
          ["dig", "Scava", <Disc3 key="i" size={14} />],
          ["expand", "Espandi playlist", <Wand2 key="i" size={14} />],
        ] as const).map(([m, label, icon]) => (
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
            {icon} {label}
          </button>
        ))}
      </div>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {/* SCAVA (dig Discogs: genere o etichetta) */}
      {mode === "dig" && (
        <>
          <div className="mb-6 border border-border p-4">
            {/* da cosa parti */}
            <div className="mb-3 flex items-center gap-3">
              <span className="text-[10px] uppercase tracking-wider text-muted">Parti da</span>
              <div className="inline-flex rounded-none border border-border bg-surface p-0.5">
                {([
                  ["genre", "Genere", <Disc3 key="i" size={13} />],
                  ["label", "Etichetta", <Tags key="i" size={13} />],
                ] as const).map(([s, label, icon]) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => switchSeed(s)}
                    aria-pressed={digSeed === s}
                    className={cn(
                      "inline-flex items-center gap-1.5 rounded-none px-2.5 py-1 text-xs font-medium transition-colors",
                      digSeed === s ? "bg-elevated text-fg" : "text-muted hover:text-fg",
                    )}
                  >
                    {icon} {label}
                  </button>
                ))}
              </div>
            </div>

            {/* picker: genere */}
            {digSeed === "genre" && (
              <>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                  <div className="min-w-0 flex-1">
                    <Field label="Genere o stile">
                      <Input
                        list="genre-suggestions"
                        value={genre}
                        onChange={(e) => setGenre(e.target.value)}
                        disabled={busy}
                        placeholder="es. Acid House, Dub Techno, Italo-Disco…"
                      />
                      <datalist id="genre-suggestions">
                        {genres?.library.map((g) => <option key={`l-${g}`} value={g} />)}
                        {genres?.styles.map((g) => <option key={`s-${g}`} value={g} />)}
                      </datalist>
                    </Field>
                  </div>
                  <Button onClick={runDig} disabled={busy || !genre.trim()}>
                    {busy ? <Spinner /> : <Disc3 size={15} />} Scava
                  </Button>
                </div>
                {quickGenres.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {quickGenres.map((g) => (
                      <Chip key={g} on={genre === g} onClick={() => setGenre(g)} disabled={busy}>{g}</Chip>
                    ))}
                  </div>
                )}
              </>
            )}

            {/* picker: etichetta */}
            {digSeed === "label" && (
              <>
                {noLabels ? (
                  <p className="text-sm text-muted">
                    Nessuna etichetta in libreria: recuperale dalla sezione Etichette, oppure scava per genere.
                  </p>
                ) : (
                  <>
                    <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                      <span className="text-[10px] uppercase tracking-wider text-muted">Scegli un’etichetta</span>
                      <Button onClick={runDig} disabled={busy || !selectedLabel}>
                        {busy ? <Spinner /> : <Disc3 size={15} />} Scava
                      </Button>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {visibleLabels.map((l) => (
                        <Chip key={l.label} on={selectedLabel === l.label} onClick={() => setSelectedLabel(l.label)} disabled={busy}>
                          {l.label}
                        </Chip>
                      ))}
                      {(hiddenLabelCount > 0 || showAllLabels) && (labels?.length ?? 0) > CHIP_CAP && (
                        <button
                          type="button"
                          onClick={() => setShowAllLabels((v) => !v)}
                          className="rounded-none px-2.5 py-1 text-xs text-muted underline underline-offset-4 transition-colors hover:text-fg"
                        >
                          {showAllLabels ? "− meno" : `+${hiddenLabelCount} altre`}
                        </button>
                      )}
                    </div>
                  </>
                )}
              </>
            )}

            {/* preset profondità */}
            <div className="mt-4 flex flex-wrap items-center gap-3">
              <span className="text-[10px] uppercase tracking-wider text-muted">Quanto osare</span>
              <div className="inline-flex rounded-none border border-border bg-surface p-0.5">
                {PRESETS.map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    onClick={() => setAdventurousness(p.value)}
                    aria-pressed={activePreset.key === p.key}
                    disabled={busy}
                    className={cn(
                      "rounded-none px-2.5 py-1 text-xs font-medium transition-colors",
                      activePreset.key === p.key ? "bg-elevated text-fg" : "text-muted hover:text-fg",
                    )}
                  >
                    {p.label}
                  </button>
                ))}
              </div>
              <span className="text-xs text-muted">{activePreset.desc}</span>
            </div>

            <p className="mt-3 text-xs leading-relaxed text-muted">
              Tanti brani dello stesso suono da scavare (via Discogs), già ripuliti dal rumore.
              Salva quelli che ti piacciono: l’identità Spotify si risolve dopo.
            </p>
          </div>

          {busy && !dig && (
            <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> Scavo nelle crate…</div>
          )}
          {dig && <LeadResults dig={dig} />}
          {!busy && !dig && (
            <EmptyState icon={<Disc3 size={28} />} title="Pronto per scavare">
              {digReady
                ? "Premi “Scava” per esplorare a fondo."
                : "Scegli un genere o un’etichetta qui sopra, poi premi “Scava”."}
            </EmptyState>
          )}
        </>
      )}

      {/* ESPANDI PLAYLIST */}
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
              Importa una playlist dalla sezione Playlist per poterla espandere.
            </EmptyState>
          )}
          {expandReady && (
            <>
              <div className="mb-6 border border-border p-4">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                  <div className="min-w-0 flex-1">
                    <Field label="Playlist da espandere">
                      <Select value={playlistId ?? ""} onChange={(e) => setPlaylistId(Number(e.target.value))} disabled={busy}>
                        {playlists?.map((p) => (
                          <option key={p.id} value={p.id}>{p.name} · {p.track_count} tracce</option>
                        ))}
                      </Select>
                    </Field>
                  </div>
                  <Checkbox
                    label={status?.ai_explanations ? "Spiega con l'AI" : "Spiegazioni AI (configura AI_API_KEY)"}
                    checked={aiEnabled}
                    onChange={setUseAi}
                    disabled={busy || !status?.ai_explanations}
                  />
                  <Button onClick={runExpand} disabled={busy || playlistId == null}>
                    {busy ? <Spinner /> : <Wand2 size={15} />} Scopri tracce affini
                  </Button>
                </div>
                <p className="mt-3 text-xs leading-relaxed text-muted">
                  Tracce di gusto affine, già risolte su Spotify per aggiungerle subito alla playlist.
                </p>
              </div>

              {busy && !result && (
                <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> Cerco tracce…</div>
              )}
              {result && <Results result={result} />}
              {!busy && !result && (
                <EmptyState icon={<Compass size={28} />} title="Pronto per il discovery">
                  Scegli una playlist qui sopra e premi “Scopri tracce affini”.
                </EmptyState>
              )}
            </>
          )}
        </>
      )}
    </PageLayout>
  );
}

function Chip({ on, onClick, disabled, children }: { on: boolean; onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      disabled={disabled}
      className={cn(
        "rounded-none border px-2.5 py-1 text-xs transition-colors",
        on
          ? "border-border-strong bg-elevated text-fg"
          : "border-border bg-surface text-muted hover:border-border-strong hover:text-fg",
      )}
    >
      {children}
    </button>
  );
}

function LeadResults({ dig }: { dig: DiscoveryDigResponse }) {
  if (dig.leads.length === 0) {
    return (
      <EmptyState icon={<Disc3 size={28} />} title="Niente da scavare">
        Nessun brano nuovo per “{dig.value}”. Prova un altro {dig.seed_type === "label" ? "valore" : "stile"} o alza l’audacia.
      </EmptyState>
    );
  }
  return (
    <div>
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">
        {dig.leads.length} da esplorare · {dig.value}
      </h2>
      <div className="grid gap-2">
        {dig.leads.map((l, i) => (
          <LeadRow key={`${l.artist}-${l.title}-${i}`} l={l} />
        ))}
      </div>
    </div>
  );
}

function LeadRow({ l }: { l: DiscoveryLead }) {
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  const spotifySearch = `https://open.spotify.com/search/${encodeURIComponent(`${l.artist} ${l.title}`)}`;
  const linkCls =
    "inline-flex items-center gap-1 rounded-none border border-border-strong px-2.5 py-1.5 text-xs font-medium text-fg transition-colors hover:bg-elevated";

  const add = async () => {
    setAdding(true);
    setAddError(null);
    try {
      await discoveryAddLead(l);
      setAdded(true);
    } catch (e) {
      setAddError(err(e));
    } finally {
      setAdding(false);
    }
  };

  return (
    <Card className="flex items-center gap-3 p-3">
      {l.thumb_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={l.thumb_url} alt="" className="h-12 w-12 shrink-0 rounded-none object-cover" />
      ) : (
        <div className="grid h-12 w-12 shrink-0 place-items-center rounded-none bg-elevated text-faint">
          <Disc3 size={18} />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium">{l.artist} — {l.title}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-faint">
          {l.style && <span>{l.style}</span>}
          {l.label && <span>· {l.label}</span>}
          {l.year != null && <span>· {l.year}</span>}
          <span>· {l.have} in collezione</span>
          {l.want > 0 && <span>· {l.want} cercano</span>}
        </div>
        {addError && <p className="mt-1 text-xs text-danger">⚠ {addError}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {l.discogs_url && (
          <a href={l.discogs_url} target="_blank" rel="noreferrer" className={linkCls}>
            <ExternalLink size={13} /> Discogs
          </a>
        )}
        <a href={spotifySearch} target="_blank" rel="noreferrer" className={linkCls}>
          <Search size={13} /> Spotify
        </a>
        <Button size="sm" variant={added ? "ghost" : "outline"} onClick={add} disabled={adding || added}>
          {added ? <><Check size={14} /> Salvato</> : adding ? <Spinner /> : <><Plus size={14} /> Salva</>}
        </Button>
      </div>
    </Card>
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
