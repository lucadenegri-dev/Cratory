"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
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
import { useT } from "@/lib/i18n";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

type DigSeed = "genre" | "label";
const CHIP_CAP = 12;

function DiscoveryInner() {
  const t = useT();
  const jobs = useJobs();

  const PRESETS: { key: string; label: string; value: number; desc: string }[] = [
    { key: "familiare", label: t.discovery.presetFamiliarLabel, value: 0.15, desc: t.discovery.presetFamiliarDesc },
    { key: "bilanciato", label: t.discovery.presetBalancedLabel, value: 0.45, desc: t.discovery.presetBalancedDesc },
    { key: "avventuroso", label: t.discovery.presetAdventurousLabel, value: 0.85, desc: t.discovery.presetAdventurousDesc },
  ];

  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const initialSeed = (searchParams.get("seed") === "label" ? "label" : "genre") as DigSeed;
  const initialValue = searchParams.get("value") ?? "";
  const initialAdv = Number(searchParams.get("adv") ?? "0.45");
  const initialTaste = searchParams.get("taste");

  // riferimento di gusto (playlist) per il dig
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);

  // scava (dig Discogs)
  const [digSeed, setDigSeed] = useState<DigSeed>(initialSeed);
  const [genres, setGenres] = useState<DiscoveryGenres | null>(null);
  const [genre, setGenre] = useState<string>(initialSeed === "genre" ? initialValue : "");
  const [labels, setLabels] = useState<LabelStats[] | null>(null);
  const [selectedLabel, setSelectedLabel] = useState<string>(initialSeed === "label" ? initialValue : "");
  const [showAllLabels, setShowAllLabels] = useState(false);
  const [adventurousness, setAdventurousness] = useState(
    Number.isFinite(initialAdv) ? Math.min(1, Math.max(0, initialAdv)) : 0.45,
  );
  const [tasteRef, setTasteRef] = useState<number | null>(initialTaste ? Number(initialTaste) : null); // null = tutta la libreria
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
        if (!initialValue) setGenre(g.library[0] ?? g.styles[0] ?? "");
      })
      .catch(() => setGenres({ library: [], styles: [] }));
    getLabels()
      .then((ls) => {
        setLabels(ls);
        if (!initialValue && ls.length) setSelectedLabel(ls[0].label);
      })
      .catch(() => setLabels([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const switchSeed = (s: DigSeed) => {
    setDigSeed(s);
    setDig(null);
    setError(null);
  };

  const executeDig = useCallback(
    async (seed: DigSeed, value: string, adv: number, taste: number | null) => {
      setBusy(true);
      setError(null);
      setDig(null);
      jobs.startClientJob("dig", t.jobs.dig);
      jobs.updateClientJob("dig", { detail: `Discogs · ${value}` });
      try {
        setDig(await discoveryDig(seed, value, { adventurousness: adv, tastePlaylistId: taste }));
      } catch (e) {
        setError(err(e));
      } finally {
        setBusy(false);
        jobs.endClientJob("dig");
      }
    },
    [jobs, t],
  );

  const paramsKey = searchParams.toString();
  useEffect(() => {
    const seed: DigSeed = searchParams.get("seed") === "label" ? "label" : "genre";
    const value = searchParams.get("value") ?? "";
    if (!value) return; // pagina aperta senza un dig: mostra l'empty state, non eseguire
    const advRaw = Number(searchParams.get("adv") ?? "0.45");
    const adv = Number.isFinite(advRaw) ? Math.min(1, Math.max(0, advRaw)) : 0.45;
    const tasteRaw = Number(searchParams.get("taste"));
    const taste = Number.isFinite(tasteRaw) && tasteRaw > 0 ? tasteRaw : null;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- il dig è l'external system: l'effect risincronizza i risultati sull'URL (query string), non su state locale
    executeDig(seed, value, adv, taste);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paramsKey]);

  const runDig = () => {
    const value = digSeed === "genre" ? genre.trim() : selectedLabel;
    if (!value) return;
    const params = new URLSearchParams();
    params.set("seed", digSeed);
    params.set("value", value);
    params.set("adv", String(adventurousness));
    if (tasteRef != null) params.set("taste", String(tasteRef));
    // Params identici a quelli già nell'URL: la ricerca è deterministica, il
    // risultato sarebbe lo stesso. Non pushare, così non si accumula una voce
    // di cronologia duplicata (back richiederebbe due click).
    if (params.toString() === searchParams.toString()) return;
    router.push(`${pathname}?${params.toString()}`, { scroll: false });
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
      <p className="mb-4 text-sm text-muted">{t.discovery.intro}</p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {/* DIG (Discogs: genere o etichetta) */}
      <div className="mb-6 border border-border p-4">
            {/* riga alta: Parti da (sx) + preset profondità e DIG (dx) */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.startFromLabel}</span>
                <div className="inline-flex rounded-none border border-border bg-surface p-0.5">
                  {([
                    ["genre", t.discovery.seedGenre, <Disc3 key="i" size={13} />],
                    ["label", t.discovery.seedLabel, <Tags key="i" size={13} />],
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
                  {busy ? <Spinner /> : <Disc3 size={15} />} {t.discovery.dig}
                </Button>
              </div>
            </div>

            {/* riferimento di gusto: rispetto a cosa misurare l'affinità */}
            {(playlists?.length ?? 0) > 0 && (
              <div className="mt-3 flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.affinityLabel}</span>
                <Select
                  value={tasteRef ?? ""}
                  onChange={(e) => setTasteRef(e.target.value ? Number(e.target.value) : null)}
                  disabled={busy}
                >
                  <option value="">{t.discovery.wholeLibraryOption}</option>
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
                  placeholder={t.discovery.genrePlaceholder}
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
                    {t.discovery.noLabels}
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
                        {showAllLabels ? t.discovery.showLess : t.discovery.showMore(hiddenLabelCount)}
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {busy && !dig && (
            <Loading label={t.discovery.digInProgress} />
          )}
          {dig && <DiscoveryLeadGrid dig={dig} />}
          {!busy && !dig && (
            <EmptyState icon={<Disc3 size={28} />} title={t.discovery.readyTitle}>
              {digReady
                ? t.discovery.readyBodyReady
                : t.discovery.readyBodyNotReady}
            </EmptyState>
          )}
    </PageLayout>
  );
}

export default function DiscoveryPage() {
  return (
    <Suspense>
      <DiscoveryInner />
    </Suspense>
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
