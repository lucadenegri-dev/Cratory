"use client";

import { useEffect, useState } from "react";
import { Disc3, Tags } from "lucide-react";
import {
  discoveryDig,
  getDiscoveryGenres,
  listImportedPlaylists,
  getLabels,
  type DiscoveryDigResponse,
  type DiscoveryGenres,
  type Playlist,
  type LabelStats,
} from "@/lib/api";
import { Alert, Button, EmptyState, Spinner, Select, Input, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { cn } from "@/lib/cn";
import { DiscoveryLeadGrid } from "@/components/discovery-lead-grid";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
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
    jobs.updateClientJob("dig", { detail: `Discogs · ${value}` });
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
            <Loading label="DIG in corso…" />
          )}
          {dig && <DiscoveryLeadGrid dig={dig} />}
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
