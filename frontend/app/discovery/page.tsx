"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Plus, Check, Disc3, Search, Tags, Download } from "lucide-react";
import {
  discoveryDig,
  discoveryAddLead,
  getDiscoveryGenres,
  listImportedPlaylists,
  getLabels,
  downloadCandidates,
  downloadTrack,
  type DiscoveryDigResponse,
  type DiscoveryLead,
  type Reason,
  type DiscoveryGenres,
  type Playlist,
  type LabelStats,
  type DownloadCandidate,
} from "@/lib/api";
import { Card, Alert, Button, EmptyState, Spinner, Select, Input, Modal } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { cn } from "@/lib/cn";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

function reasonLabel(r: Reason): string {
  switch (r.code) {
    case "rare_wanted":
      return `raro & richiesto ${r.data.have}/${r.data.want}`;
    case "deep_cut":
      return "deep cut";
    case "label_followed":
      return `etichetta che segui${r.data.label ? ` · ${r.data.label}` : ""}`;
    case "artist_collected":
      return "artista che collezioni";
    case "style_match":
      return "stile che ascolti";
    case "recent":
      return `recente${r.data.year ? ` · ${r.data.year}` : ""}`;
    default:
      return r.code;
  }
}

type DigSeed = "genre" | "label";
const CHIP_CAP = 12;

const PRESETS: { key: string; label: string; value: number; desc: string }[] = [
  { key: "familiare", label: "Familiare", value: 0.15, desc: "Artisti e nomi che probabilmente conosci già." },
  { key: "bilanciato", label: "Bilanciato", value: 0.45, desc: "Un mix tra noto e nuovo." },
  { key: "avventuroso", label: "Avventuroso", value: 0.85, desc: "Rarità e deep cut richiesti che non conosci." },
];

export default function DiscoveryPage() {
  const jobs = useJobs();

  // riferimento di gusto (playlist) per il dig
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);

  // scava (dig Discogs)
  const [digSeed, setDigSeed] = useState<DigSeed>("genre");
  const [genres, setGenres] = useState<DiscoveryGenres | null>(null);
  const [genre, setGenre] = useState<string>("");
  const [labels, setLabels] = useState<LabelStats[] | null>(null);
  const [selectedLabel, setSelectedLabel] = useState<string>("");
  const [showAllLabels, setShowAllLabels] = useState(false);
  const [adventurousness, setAdventurousness] = useState(0.45);
  const [tasteRef, setTasteRef] = useState<number | null>(null); // null = tutta la libreria
  const [dig, setDig] = useState<DiscoveryDigResponse | null>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listImportedPlaylists()
      .then(setPlaylists)
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

  const switchSeed = (s: DigSeed) => {
    setDigSeed(s);
    setDig(null);
    setError(null);
  };

  const runDig = async () => {
    const value = digSeed === "genre" ? genre.trim() : selectedLabel;
    if (!value) return;
    setBusy(true);
    setError(null);
    setDig(null);
    jobs.startClientJob("dig", "Crate digging");
    try {
      setDig(await discoveryDig(digSeed, value, { adventurousness, tastePlaylistId: tasteRef }));
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(false);
      jobs.endClientJob("dig");
    }
  };

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
      <p className="mb-4 text-sm text-muted">Scava nuova musica per genere o etichetta.</p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {/* DIG (Discogs: genere o etichetta) */}
      <div className="mb-6 border border-border p-4">
            {/* riga alta: Parti da (sx) + preset profondità e DIG (dx) */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
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

              <div className="flex flex-wrap items-center gap-2">
                <div className="inline-flex rounded-none border border-border bg-surface p-0.5">
                  {PRESETS.map((p) => (
                    <button
                      key={p.key}
                      type="button"
                      onClick={() => setAdventurousness(p.value)}
                      aria-pressed={activePreset.key === p.key}
                      disabled={busy}
                      title={p.desc}
                      className={cn(
                        "rounded-none px-2.5 py-1 text-xs font-medium transition-colors",
                        activePreset.key === p.key ? "bg-elevated text-fg" : "text-muted hover:text-fg",
                      )}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
                <Button onClick={runDig} disabled={busy || !digReady}>
                  {busy ? <Spinner /> : <Disc3 size={15} />} DIG
                </Button>
              </div>
            </div>

            {/* riferimento di gusto: rispetto a cosa misurare l'affinità */}
            {(playlists?.length ?? 0) > 0 && (
              <div className="mt-3 flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wider text-muted">Affinità rispetto a</span>
                <Select
                  value={tasteRef ?? ""}
                  onChange={(e) => setTasteRef(e.target.value ? Number(e.target.value) : null)}
                  disabled={busy}
                >
                  <option value="">Tutta la libreria</option>
                  {playlists?.map((p) => (
                    <option key={p.id} value={p.id}>{p.name}</option>
                  ))}
                </Select>
              </div>
            )}

            {/* picker: genere */}
            {digSeed === "genre" && (
              <div className="mt-3">
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
                {quickGenres.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {quickGenres.map((g) => (
                      <Chip key={g} on={genre === g} onClick={() => setGenre(g)} disabled={busy}>{g}</Chip>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* picker: etichetta */}
            {digSeed === "label" && (
              <div className="mt-3">
                {noLabels ? (
                  <p className="text-sm text-muted">
                    Nessuna etichetta in libreria: recuperale dalla sezione Etichette, oppure scava per genere.
                  </p>
                ) : (
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
                )}
              </div>
            )}
          </div>

          {busy && !dig && (
            <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> DIG in corso…</div>
          )}
          {dig && <LeadResults dig={dig} />}
          {!busy && !dig && (
            <EmptyState icon={<Disc3 size={28} />} title="Pronto per scavare">
              {digReady
                ? "Premi “DIG” per esplorare a fondo."
                : "Scegli un genere o un’etichetta qui sopra, poi premi “DIG”."}
            </EmptyState>
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

  const [dlOpen, setDlOpen] = useState(false);
  const [dlLoading, setDlLoading] = useState(false);
  const [dlCands, setDlCands] = useState<DownloadCandidate[]>([]);
  const [dlError, setDlError] = useState<string | null>(null);
  const [dlDone, setDlDone] = useState(false);

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

  const openDownload = async () => {
    setDlOpen(true);
    setDlLoading(true);
    setDlError(null);
    try {
      setDlCands(await downloadCandidates(l.artist, l.title));
    } catch (e) {
      setDlError(err(e));
    } finally {
      setDlLoading(false);
    }
  };

  const pick = async (cand: DownloadCandidate) => {
    setDlLoading(true);
    setDlError(null);
    try {
      const { track } = await discoveryAddLead(l);
      await downloadTrack(track.id, cand);
      setDlDone(true);
      setDlOpen(false);
    } catch (e) {
      setDlError(err(e));
    } finally {
      setDlLoading(false);
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
        {l.reasons.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {l.reasons.map((r, i) => (
              <span
                key={`${r.code}-${i}`}
                className="inline-flex items-center rounded-none border border-border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-muted"
              >
                {reasonLabel(r)}
              </span>
            ))}
          </div>
        )}
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
        <Button size="sm" variant={dlDone ? "ghost" : "outline"} onClick={openDownload} disabled={dlDone}>
          {dlDone ? <><Check size={14} /> Scaricato</> : <><Download size={14} /> Download</>}
        </Button>
      </div>
      <Modal open={dlOpen} onClose={() => setDlOpen(false)} title={`Download — ${l.artist} ${l.title}`}>
        {dlError && <Alert tone="danger">⚠ {dlError}</Alert>}
        {dlLoading && <p className="text-sm text-faint">Ricerca su Soulseek…</p>}
        {!dlLoading && !dlError && dlCands.length === 0 && (
          <p className="text-sm text-faint">Nessun candidato trovato su Soulseek.</p>
        )}
        <ul className="divide-y divide-border">
          {dlCands.map((c, i) => (
            <li key={`${c.username}-${i}`} className="flex items-center justify-between gap-2 py-2">
              <div className="min-w-0">
                <div className="truncate text-sm">{c.filename.split(/[\\/]/).pop()}</div>
                <div className="text-xs text-faint">
                  {c.format?.toUpperCase()} {c.bitrate ? `· ${c.bitrate}kbps` : ""} · conf {Math.round(c.confidence * 100)}%
                </div>
              </div>
              <Button size="sm" variant="outline" onClick={() => pick(c)} disabled={dlLoading}>
                <Download size={13} /> Scarica
              </Button>
            </li>
          ))}
        </ul>
      </Modal>
    </Card>
  );
}
