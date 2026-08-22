"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import {
  Sparkles, Wand2, ListMusic, Music4, Cpu, HelpCircle,
  TrendingUp, SlidersHorizontal, ArrowRight, Sunrise, Flame, Sunset, ChevronDown,
} from "lucide-react";
import {
  apiGet, apiPost, errText,
  type AiStatus, type GenStatus, type Playlist,
} from "@/lib/api";
import { Card, Button, Input, Textarea, Select, Field, Checkbox, EqMeter, Alert, EmptyState } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

const STRATEGY_DEFS = [
  { value: "smooth", key: "smooth" },
  { value: "progressive", key: "progressive" },
  { value: "contrast", key: "contrast" },
  { value: "experimental", key: "experimental" },
  { value: "peak_time", key: "peakTime" },
  { value: "warm_up", key: "warmUp" },
  { value: "closing", key: "closing" },
] as const;
const SOURCE_VALUES = ["spotify", "manual"] as const;
// Identità stabile (non la label tradotta, che cambia con la lingua): il preset resta
// "attivo" a colpo d'occhio anche dopo un toggle IT/EN.
const PRESETS = [
  { key: "warmUp", icon: Sunrise, strategy: "warm_up", duration: 45, startBpm: "118", endBpm: "124", startEnergy: "30", endEnergy: "55" },
  { key: "peakTime", icon: Flame, strategy: "peak_time", duration: 60, startBpm: "126", endBpm: "132", startEnergy: "70", endEnergy: "92" },
  { key: "progressive", icon: TrendingUp, strategy: "progressive", duration: 90, startBpm: "120", endBpm: "130", startEnergy: "40", endEnergy: "85" },
  { key: "closing", icon: Sunset, strategy: "closing", duration: 45, startBpm: "128", endBpm: "120", startEnergy: "78", endEnergy: "40" },
] as const;

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div className="mt-5 border-t border-border pt-5 first:mt-0 first:border-0 first:pt-0">
      <div className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted">{icon}{title}</div>
      {children}
    </div>
  );
}

function ArcField({ label, hint, from, to }: { label: string; hint?: string; from: React.ReactNode; to: React.ReactNode }) {
  return (
    <div>
      <span className="mb-1.5 block text-xs font-medium uppercase tracking-wide text-muted">{label}</span>
      <div className="flex items-center gap-2">
        <div className="flex-1">{from}</div>
        <ArrowRight size={14} className="shrink-0 text-faint" />
        <div className="flex-1">{to}</div>
      </div>
      {hint && <span className="mt-1 block text-xs text-faint">{hint}</span>}
    </div>
  );
}

function SetBuilderInner() {
  const t = useT();
  const SOURCES = SOURCE_VALUES.map((value) => ({ value, label: value === "spotify" ? "Spotify" : t.setBuilder.sourceManual }));
  const router = useRouter();
  const searchParams = useSearchParams();
  const [duration, setDuration] = useState(45);
  const [startBpm, setStartBpm] = useState("");
  const [endBpm, setEndBpm] = useState("");
  const [seedArtists, setSeedArtists] = useState("");
  const [strategy, setStrategy] = useState("smooth");
  const [maxPerArtist, setMaxPerArtist] = useState(2);
  const [sources, setSources] = useState<string[]>([]);
  const [avoidShort, setAvoidShort] = useState(true);
  const [ownedOnly, setOwnedOnly] = useState(true);
  const [prompt, setPrompt] = useState("");
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [useAi, setUseAi] = useState(false);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  // Pre-selezione da ?playlist=… letta una sola volta all'inizializzazione (no setState in effect).
  const [playlistId, setPlaylistId] = useState(() => searchParams.get("playlist") ?? "");
  const [startEnergy, setStartEnergy] = useState("");
  const [endEnergy, setEndEnergy] = useState("");
  const [genres, setGenres] = useState<{ genre: string; count: number }[]>([]);
  const [selGenres, setSelGenres] = useState<string[]>([]);
  const [activePreset, setActivePreset] = useState<string | null>(null);

  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  // Unico poller (JobsProvider): la generazione gira anche nella barra job globale.
  // Il riaggancio a una generazione già in corso al mount (es. AI avviata prima di
  // navigare via) è automatico: `busy` legge lo stato del provider.
  const jobs = useJobs();
  const generation = jobs.generation;
  const busy = generation?.status === "running";

  useEffect(() => {
    // Il default è il motore deterministico: l'AI si sceglie esplicitamente.
    apiGet<AiStatus>("/api/ai/status").then(setAiStatus).catch(() => setAiStatus({ configured: false, model: null }));
    apiGet<Playlist[]>("/api/playlists").then(setPlaylists).catch(() => {});
    apiGet<{ genre: string; count: number }[]>("/api/library/genres").then(setGenres).catch(() => {});
  }, []);

  // Cronometro "elapsed": riparte da 0 ogni volta che una generazione diventa attiva
  // (avviata qui o già in corso al mount), si ferma (senza azzerarsi) a fine job.
  // Il primo giro è schedulato (non un setState sincrono nel corpo dell'effect).
  useEffect(() => {
    if (!busy) return;
    const t0 = Date.now();
    const tick = () => setElapsed(Math.floor((Date.now() - t0) / 1000));
    const immediate = setTimeout(tick, 0);
    const id = setInterval(tick, 1000);
    return () => { clearTimeout(immediate); clearInterval(id); };
  }, [busy]);

  // Alla transizione running -> done/error (vista dal provider) la pagina naviga al
  // workbench o mostra l'errore, esattamente come faceva il poller locale prima.
  const prevGenStatus = useRef<string | null>(null);
  // Guardia anti-doppio-invio sincrona: `busy` deriva dal provider e si aggiorna
  // solo alla poll successiva, quindi due click ravvicinati la superano entrambi.
  const submittingRef = useRef(false);
  useEffect(() => {
    const status = generation?.status ?? null;
    if (prevGenStatus.current === "running" && status === "done" && generation?.setlist_id != null) {
      // Il set nasce nel workbench: si apre lì per riordinare, sostituire tracce e vederne l'arco.
      router.push(`/sets/detail?id=${generation.setlist_id}`);
    } else if (prevGenStatus.current === "running" && status === "error") {
      setError(generation?.error ?? t.setBuilder.generationFailed);
    }
    prevGenStatus.current = status;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generation?.status]);

  function toggleSource(s: string) {
    setSources((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  }

  function toggleGenre(g: string) {
    setSelGenres((cur) => (cur.includes(g) ? cur.filter((x) => x !== g) : [...cur, g]));
  }

  function applyPreset(p: (typeof PRESETS)[number]) {
    setStrategy(p.strategy);
    setDuration(p.duration);
    setStartBpm(p.startBpm);
    setEndBpm(p.endBpm);
    setStartEnergy(p.startEnergy);
    setEndEnergy(p.endEnergy);
    setActivePreset(p.key);
  }
  // Un preset imposta arco + strategia + durata: appena uno di quei campi cambia a mano, il preset non è più "attivo".
  const clearPreset = () => setActivePreset(null);

  const generate = useCallback(async () => {
    if (busy || submittingRef.current) return;
    submittingRef.current = true;
    setError(null);
    try {
      const started = await apiPost<GenStatus>("/api/sets/generate-async", {
        playlist_id: playlistId ? Number(playlistId) : null,
        target_duration_minutes: duration,
        start_bpm: startBpm ? Number(startBpm) : null,
        end_bpm: endBpm ? Number(endBpm) : null,
        start_energy: startEnergy ? Number(startEnergy) : null,
        end_energy: endEnergy ? Number(endEnergy) : null,
        genres: selGenres,
        seed_artists: seedArtists.split(",").map((s) => s.trim()).filter(Boolean),
        strategy,
        max_tracks_per_artist: maxPerArtist,
        sources,
        avoid_short_tracks: avoidShort,
        owned_only: ownedOnly,
        prompt: useAi ? prompt || null : null,
        use_ai: useAi,
      });
      // Seed del guard di redirect: se la generazione è velocissima la prima poll
      // del provider potrebbe vedere già "done" senza mai passare da "running", e
      // il redirect al workbench (che richiede prevGenStatus === "running") non
      // scatterebbe. La risposta del POST è "running": la registriamo qui.
      if (started?.status === "running" || started?.status === "done") {
        prevGenStatus.current = "running";
      }
      // La barra job globale aggancia subito la generazione (stessa griglia degli altri job).
      jobs.refresh();
    } catch (e) {
      setError(errText(e));
    } finally {
      submittingRef.current = false;
    }
  }, [busy, playlistId, duration, startBpm, endBpm, startEnergy, endEnergy, selGenres, seedArtists, strategy, maxPerArtist, sources, avoidShort, ownedOnly, prompt, useAi, jobs]);

  const aiReady = !!aiStatus?.configured;

  return (
    <PageLayout
      title="Set Builder"
      action={
        <Link href="/set-builder/guida" title={t.setBuilder.guideLinkTitle}
          className="inline-flex items-center gap-1.5 text-xs uppercase tracking-wider text-muted transition-colors hover:text-fg">
          <HelpCircle size={15} />
          {t.setBuilder.guideLinkLabel}
        </Link>
      }
    >
      <p className="mb-6 text-sm text-muted">
        {t.setBuilder.intro}{" "}
        {t.setBuilder.guidePrompt}{" "}
        <Link href="/set-builder/guida" className="text-fg underline underline-offset-2 transition-colors hover:text-faint">
          {t.setBuilder.guideLinkText}
        </Link>
        .
      </p>

      <div onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") generate(); }}>
        <Card className="mb-6">
          <div className="p-5">
            <Section icon={<Music4 size={13} className="text-faint" />} title={t.setBuilder.sectionBase}>
              <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
                <Field label={t.setBuilder.startPlaylistLabel}>
                  <Select value={playlistId} onChange={(e) => setPlaylistId(e.target.value)}>
                    <option value="">{t.setBuilder.wholeLibraryOption}</option>
                    {playlists.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.track_count}</option>)}
                  </Select>
                </Field>
                <Field label={t.setBuilder.durationLabel}><Input type="number" min={1} value={duration} onChange={(e) => { setDuration(Number(e.target.value)); clearPreset(); }} /></Field>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="text-xs text-muted">{t.setBuilder.quickPresetsLabel}</span>
                {PRESETS.map((p) => {
                  const Icon = p.icon;
                  const on = activePreset === p.key;
                  return (
                    <button key={p.key} type="button" onClick={() => applyPreset(p)} aria-pressed={on}
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-none border px-3 py-1 text-xs font-medium transition-colors",
                        on
                          ? "border-border-strong bg-elevated text-fg"
                          : "border-border bg-surface text-muted hover:border-border-strong hover:text-fg",
                      )}>
                      <Icon size={13} /> {t.setBuilder.presets[p.key]}
                    </button>
                  );
                })}
              </div>
              {activePreset && (
                <p className="mt-2 text-xs text-muted">
                  {t.setBuilder.presetSummaryLabel(
                    t.setBuilder.strategies[STRATEGY_DEFS.find((s) => s.value === strategy)?.key ?? "smooth"].label,
                    duration,
                    startBpm,
                    endBpm,
                    startEnergy,
                    endEnergy,
                  )}
                </p>
              )}
            </Section>

            <Section icon={<Cpu size={13} className="text-faint" />} title={t.setBuilder.sectionEngine}>
              <div className="flex flex-wrap items-center gap-3">
                <div role="group" aria-label={t.setBuilder.engineGroupAria} className="inline-flex rounded-none border border-border bg-surface p-1">
                  <button
                    type="button"
                    aria-pressed={!useAi}
                    onClick={() => setUseAi(false)}
                    className={cn("rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
                      !useAi ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
                  >
                    {t.setBuilder.curationOffLabel}
                  </button>
                  <button
                    type="button"
                    aria-pressed={useAi}
                    disabled={!aiReady}
                    onClick={() => setUseAi(true)}
                    title={aiReady ? undefined : t.setBuilder.aiNotConfiguredTitle}
                    className={cn("inline-flex items-center gap-1.5 rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                      useAi ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
                  >
                    <Sparkles size={13} /> {t.setBuilder.curationOnLabel}
                  </button>
                </div>
                <span className="text-xs text-muted">
                  {useAi
                    ? <>{t.setBuilder.curationOnDesc}{aiStatus?.model && <span className="text-faint"> · {aiStatus.model}</span>}</>
                    : <>{t.setBuilder.curationOffDesc}</>}
                </span>
              </div>
              {!aiReady && (
                <p className="mt-2 text-xs text-muted">{t.setBuilder.aiConfigPrefix} <code className="rounded-none bg-elevated px-1">AI_API_KEY</code> {t.setBuilder.aiConfigMiddle} <Link href="/settings" className="text-fg underline-offset-4 hover:underline">{t.nav.settings}</Link>{t.setBuilder.aiConfigSuffix}</p>
              )}
            </Section>

            {useAi && aiReady && (
              <Section icon={<Sparkles size={13} className="text-faint" />} title={t.setBuilder.sectionAiGuidance}>
                <Field label={t.setBuilder.freePromptLabel}>
                  <Textarea rows={2} placeholder={t.setBuilder.freePromptPlaceholder}
                    value={prompt} onChange={(e) => setPrompt(e.target.value)} />
                </Field>
              </Section>
            )}

            <details className="group mt-5 border-t border-border pt-5">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-semibold uppercase tracking-wide text-muted transition-colors hover:text-fg [&::-webkit-details-marker]:hidden">
                <span className="flex items-center gap-1.5"><SlidersHorizontal size={13} className="text-faint" /> {t.setBuilder.advancedOptionsLabel}</span>
                <ChevronDown size={15} className="text-faint transition-transform duration-200 group-open:rotate-180" />
              </summary>
              <div className="mt-4">
                <Section icon={<TrendingUp size={13} className="text-faint" />} title={t.setBuilder.sectionArc}>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <ArcField label="BPM" hint={t.setBuilder.bpmHint}
                      from={<Input type="number" placeholder={t.setBuilder.fromPlaceholder} value={startBpm} onChange={(e) => { setStartBpm(e.target.value); clearPreset(); }} />}
                      to={<Input type="number" placeholder={t.setBuilder.toPlaceholder} value={endBpm} onChange={(e) => { setEndBpm(e.target.value); clearPreset(); }} />} />
                    <ArcField label={t.setBuilder.energyLabel} hint={t.setBuilder.energyHint}
                      from={<Input type="number" min={0} max={100} placeholder={t.setBuilder.fromPlaceholder} value={startEnergy} onChange={(e) => { setStartEnergy(e.target.value); clearPreset(); }} />}
                      to={<Input type="number" min={0} max={100} placeholder={t.setBuilder.toPlaceholder} value={endEnergy} onChange={(e) => { setEndEnergy(e.target.value); clearPreset(); }} />} />
                  </div>
                </Section>

                <Section icon={<SlidersHorizontal size={13} className="text-faint" />} title={t.setBuilder.sectionConstraints}>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <Field label={t.setBuilder.strategyLabel} hint={t.setBuilder.strategies[STRATEGY_DEFS.find((s) => s.value === strategy)?.key ?? "smooth"]?.desc}>
                      <Select value={strategy} onChange={(e) => { setStrategy(e.target.value); clearPreset(); }}>
                        {STRATEGY_DEFS.map((s) => <option key={s.value} value={s.value}>{t.setBuilder.strategies[s.key].label}</option>)}
                      </Select>
                    </Field>
                    <Field label={t.setBuilder.maxPerArtistLabel}><Input type="number" min={1} value={maxPerArtist} onChange={(e) => setMaxPerArtist(Number(e.target.value))} /></Field>
                    <Field label={t.setBuilder.seedArtistsLabel}>
                      <Input placeholder={t.setBuilder.seedArtistsPlaceholder} value={seedArtists} onChange={(e) => setSeedArtists(e.target.value)} />
                    </Field>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
                    <Checkbox label={t.setBuilder.avoidShortLabel} checked={avoidShort} onChange={setAvoidShort} />
                    <Checkbox label={t.setBuilder.ownedOnlyLabel} checked={ownedOnly} onChange={setOwnedOnly} />
                    {SOURCES.map((s) => (
                      <Checkbox key={s.value} label={t.setBuilder.onlySourceLabel(s.label)} checked={sources.includes(s.value)} onChange={() => toggleSource(s.value)} />
                    ))}
                  </div>

                  {genres.length > 0 && (
                    <div className="mt-4">
                      <span className="mb-2 block text-[10px] font-medium uppercase tracking-wider text-muted">
                        {t.setBuilder.genresLabel} {selGenres.length > 0 && <span className="text-faint">· {t.setBuilder.genresSelectedLabel(selGenres.length)}</span>}
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {genres.slice(0, 20).map(({ genre, count }) => {
                          const on = selGenres.includes(genre);
                          return (
                            <button
                              key={genre}
                              type="button"
                              onClick={() => toggleGenre(genre)}
                              aria-pressed={on}
                              className={cn(
                                "inline-flex items-center gap-1.5 rounded-none border px-2.5 py-1 text-xs transition-colors",
                                on
                                  ? "border-border-strong bg-elevated text-fg"
                                  : "border-border bg-surface text-muted hover:border-border-strong hover:text-fg",
                              )}
                            >
                              {genre} <span className="tnum text-faint">{count}</span>
                            </button>
                          );
                        })}
                      </div>
                      <span className="mt-1.5 block text-xs text-faint">{t.setBuilder.genresHint}</span>
                    </div>
                  )}
                </Section>
              </div>
            </details>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
              <span className="text-xs text-faint">
                {t.setBuilder.footerEnginePrefix} <span className="text-muted">{useAi ? t.setBuilder.curationOnLabel : t.setBuilder.curationOffLabel}</span> {t.setBuilder.footerGenerateHint} <kbd className="rounded-none border border-border px-1 text-muted">⌘⏎</kbd>
              </span>
              <Button onClick={generate} disabled={busy}>
                <Wand2 size={16} /> {busy ? t.setBuilder.generateButtonBusy : t.setBuilder.generateButton}
              </Button>
            </div>
          </div>
        </Card>
      </div>

      {busy && (
        <Card className="mb-6">
          <div className="p-5">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 font-medium"><Sparkles size={15} className="text-muted" /> {generation?.phase ?? t.setBuilder.startingPhase}</span>
              <span className="tnum text-muted">{elapsed}s{generation?.using_ai && elapsed > 8 ? t.setBuilder.usuallyTakesHint : ""}</span>
            </div>
            <EqMeter value={null} className="h-6 w-full" />
            <p className="mt-2 text-xs text-faint">{t.setBuilder.readyOpensWorkbench}</p>
          </div>
        </Card>
      )}

      {error && <div className="mb-6"><Alert tone="danger">⚠ {error}</Alert></div>}

      {!busy && !error && (
        <EmptyState icon={<ListMusic size={28} />} title={t.setBuilder.emptyTitle}>
          {t.setBuilder.emptyBodyPrefix} <strong>{t.setBuilder.generateButton}</strong> {t.setBuilder.emptyBodySuffix}
        </EmptyState>
      )}
    </PageLayout>
  );
}

export default function SetBuilder() {
  // useSearchParams su pagina prerenderizzata richiede un boundary Suspense
  // (stesso pattern di app/discovery/page.tsx), altrimenti la build fallisce.
  return (
    <Suspense>
      <SetBuilderInner />
    </Suspense>
  );
}
