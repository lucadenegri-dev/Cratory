"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Sparkles, Wand2, ListMusic, Music4, Cpu,
  TrendingUp, SlidersHorizontal, ArrowRight, Sunrise, Flame, Sunset, ChevronDown,
} from "lucide-react";
import {
  apiGet, apiPost,
  type AiStatus, type GenStatus, type Playlist,
} from "@/lib/api";
import { Card, Button, Input, Textarea, Select, Field, Checkbox, EqMeter, Alert, EmptyState } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { cn } from "@/lib/cn";

const STRATEGIES: { value: string; label: string; desc: string }[] = [
  { value: "smooth", label: "Fluido", desc: "transizioni morbide, rischio minimo" },
  { value: "progressive", label: "Progressivo", desc: "energia in crescita graduale" },
  { value: "contrast", label: "Contrasti", desc: "stacchi voluti tra le tracce" },
  { value: "experimental", label: "Sperimentale", desc: "accostamenti audaci" },
  { value: "peak_time", label: "Peak time", desc: "alta energia, dritto al clou" },
  { value: "warm_up", label: "Warm-up", desc: "apertura calda, bassa intensità" },
  { value: "closing", label: "Chiusura", desc: "discesa finale, più ariosa" },
];
const SOURCES: { value: string; label: string }[] = [
  { value: "spotify", label: "Spotify" },
  { value: "manual", label: "Manuale" },
];
const PRESETS = [
  { label: "Warm-up", icon: Sunrise, strategy: "warm_up", duration: 45, startBpm: "118", endBpm: "124", startEnergy: "30", endEnergy: "55" },
  { label: "Peak time", icon: Flame, strategy: "peak_time", duration: 60, startBpm: "126", endBpm: "132", startEnergy: "70", endEnergy: "92" },
  { label: "Progressivo", icon: TrendingUp, strategy: "progressive", duration: 90, startBpm: "120", endBpm: "130", startEnergy: "40", endEnergy: "85" },
  { label: "Closing", icon: Sunset, strategy: "closing", duration: 45, startBpm: "128", endBpm: "120", startEnergy: "78", endEnergy: "40" },
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

export default function SetBuilder() {
  const router = useRouter();
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
  const [mode, setMode] = useState<"technical" | "creative">("technical");
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  // Pre-selezione da ?playlist=… letta una sola volta all'inizializzazione (no setState in effect).
  const [playlistId, setPlaylistId] = useState(() =>
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("playlist") ?? "" : "",
  );
  const [startEnergy, setStartEnergy] = useState("");
  const [endEnergy, setEndEnergy] = useState("");
  const [startMood, setStartMood] = useState("");
  const [endMood, setEndMood] = useState("");
  const [activePreset, setActivePreset] = useState<string | null>(null);

  const [job, setJob] = useState<GenStatus | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopAll = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (timerRef.current) clearInterval(timerRef.current);
    pollRef.current = timerRef.current = null;
  }, []);

  useEffect(() => {
    apiGet<AiStatus>("/api/ai/status").then((s) => { setAiStatus(s); setUseAi(s.configured); }).catch(() => setAiStatus({ configured: false, model: null }));
    apiGet<Playlist[]>("/api/playlists").then(setPlaylists).catch(() => {});
    return stopAll;
  }, [stopAll]);

  const busy = job?.status === "running";

  function toggleSource(s: string) {
    setSources((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  }

  function applyPreset(p: (typeof PRESETS)[number]) {
    setStrategy(p.strategy);
    setDuration(p.duration);
    setStartBpm(p.startBpm);
    setEndBpm(p.endBpm);
    setStartEnergy(p.startEnergy);
    setEndEnergy(p.endEnergy);
    setActivePreset(p.label);
  }
  // Un preset imposta arco + strategia + durata: appena uno di quei campi cambia a mano, il preset non è più "attivo".
  const clearPreset = () => setActivePreset(null);

  function startPolling() {
    stopAll();
    const t0 = Date.now();
    timerRef.current = setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000);
    pollRef.current = setInterval(async () => {
      try {
        const s = await apiGet<GenStatus>("/api/sets/generate-status");
        setJob(s);
        if (s.status === "done" && s.setlist_id != null) {
          stopAll();
          // Il set nasce nel workbench: si apre lì per riordinare, sostituire tracce e vederne l'arco.
          router.push(`/sets/${s.setlist_id}`);
        } else if (s.status === "error") {
          stopAll();
          setError(s.error ?? "Generazione fallita");
        }
      } catch (e) {
        stopAll();
        setError(String((e as Error).message ?? e));
      }
    }, 1500);
  }

  const generate = useCallback(async () => {
    if (busy) return;
    setError(null);
    setElapsed(0);
    try {
      const started = await apiPost<GenStatus>("/api/sets/generate-async", {
        playlist_id: playlistId ? Number(playlistId) : null,
        target_duration_minutes: duration,
        start_bpm: startBpm ? Number(startBpm) : null,
        end_bpm: endBpm ? Number(endBpm) : null,
        start_energy: startEnergy ? Number(startEnergy) : null,
        end_energy: endEnergy ? Number(endEnergy) : null,
        start_mood: startMood || null,
        end_mood: endMood || null,
        seed_artists: seedArtists.split(",").map((s) => s.trim()).filter(Boolean),
        strategy,
        max_tracks_per_artist: maxPerArtist,
        sources,
        avoid_short_tracks: avoidShort,
        owned_only: ownedOnly,
        prompt: useAi ? prompt || null : null,
        use_ai: useAi,
        mode,
      });
      setJob(started);
      startPolling();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busy, playlistId, duration, startBpm, endBpm, startEnergy, endEnergy, startMood, endMood, seedArtists, strategy, maxPerArtist, sources, avoidShort, ownedOnly, prompt, useAi, mode]);

  const aiReady = !!aiStatus?.configured;

  return (
    <PageLayout title="Set Builder">
      <p className="mb-6 text-sm text-muted">Genera una scaletta dai vincoli, o descrivi a parole il set che vuoi e lascia ragionare l&apos;AI. Il set si apre nel workbench, dove lo riordini e sostituisci le tracce.</p>

      <div onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") generate(); }}>
        <Card className="mb-6">
          <div className="p-5">
            <Section icon={<Music4 size={13} className="text-faint" />} title="Base">
              <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
                <Field label="Playlist di partenza">
                  <Select value={playlistId} onChange={(e) => setPlaylistId(e.target.value)}>
                    <option value="">Tutta la libreria</option>
                    {playlists.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.track_count}</option>)}
                  </Select>
                </Field>
                <Field label="Durata (min)"><Input type="number" min={1} value={duration} onChange={(e) => { setDuration(Number(e.target.value)); clearPreset(); }} /></Field>
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="text-xs text-muted">Preset rapidi</span>
                {PRESETS.map((p) => {
                  const Icon = p.icon;
                  const on = activePreset === p.label;
                  return (
                    <button key={p.label} type="button" onClick={() => applyPreset(p)} aria-pressed={on}
                      className={cn(
                        "inline-flex items-center gap-1.5 rounded-none border px-3 py-1 text-xs font-medium transition-colors",
                        on
                          ? "border-border-strong bg-elevated text-fg"
                          : "border-border bg-surface text-muted hover:border-border-strong hover:text-fg",
                      )}>
                      <Icon size={13} /> {p.label}
                    </button>
                  );
                })}
              </div>
            </Section>

            <Section icon={<Cpu size={13} className="text-faint" />} title="Motore">
              <div className="flex flex-wrap items-center gap-3">
                <div role="group" aria-label="Motore di generazione" className="inline-flex rounded-none border border-border bg-surface p-1">
                  <button
                    type="button"
                    aria-pressed={!useAi}
                    onClick={() => setUseAi(false)}
                    className={cn("rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
                      !useAi ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
                  >
                    Algoritmo
                  </button>
                  <button
                    type="button"
                    aria-pressed={useAi}
                    disabled={!aiReady}
                    onClick={() => setUseAi(true)}
                    title={aiReady ? undefined : "AI non configurata"}
                    className={cn("inline-flex items-center gap-1.5 rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-40",
                      useAi ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
                  >
                    <Sparkles size={13} /> AI
                  </button>
                </div>
                <span className="text-xs text-muted">
                  {useAi
                    ? <>L&apos;AI ragiona sul set{aiStatus?.model && <span className="text-faint"> · {aiStatus.model}</span>}</>
                    : <>Mix deterministico dai vincoli, senza prompt.</>}
                </span>
              </div>
              {!aiReady && (
                <p className="mt-2 text-xs text-muted">AI non configurata — imposta <code className="rounded-none bg-elevated px-1">AI_API_KEY</code> in backend/.env (vedi <Link href="/settings" className="text-fg underline-offset-4 hover:underline">Impostazioni</Link>).</p>
              )}
            </Section>

            {useAi && aiReady && (
              <Section icon={<Sparkles size={13} className="text-faint" />} title="Indicazioni & AI">
                <Field label="Prompt libero">
                  <Textarea rows={2} placeholder="Parti morbido e atmosferico, poi vira più club senza diventare techno dritta troppo presto…"
                    value={prompt} onChange={(e) => setPrompt(e.target.value)} />
                </Field>
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted">Stile AI</span>
                  <div role="group" aria-label="Stile AI" className="inline-flex rounded-none border border-border bg-surface p-1">
                    {(["technical", "creative"] as const).map((m) => (
                      <button
                        key={m}
                        type="button"
                        aria-pressed={mode === m}
                        onClick={() => setMode(m)}
                        className={cn(
                          "rounded-none px-3 py-1 text-sm font-medium transition-colors",
                          mode === m ? "bg-elevated text-fg" : "text-muted hover:text-fg",
                        )}
                      >
                        {m === "technical" ? "Tecnico" : "Creativo"}
                      </button>
                    ))}
                  </div>
                  <span className="text-xs text-muted">
                    {mode === "creative"
                      ? "L'AI usa la sua conoscenza musicale: arco emotivo, contrasti voluti, sorprese."
                      : "Mix prudente: compatibilità tecnica e progressione, senza azzardi."}
                  </span>
                </div>
              </Section>
            )}

            <details className="group mt-5 border-t border-border pt-5">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-xs font-semibold uppercase tracking-wide text-muted transition-colors hover:text-fg [&::-webkit-details-marker]:hidden">
                <span className="flex items-center gap-1.5"><SlidersHorizontal size={13} className="text-faint" /> Opzioni avanzate</span>
                <ChevronDown size={15} className="text-faint transition-transform duration-200 group-open:rotate-180" />
              </summary>
              <div className="mt-4">
                <Section icon={<TrendingUp size={13} className="text-faint" />} title="Arco del set">
                  <div className="grid gap-4 sm:grid-cols-3">
                    <ArcField label="BPM" hint="vuoto = automatico"
                      from={<Input type="number" placeholder="da" value={startBpm} onChange={(e) => { setStartBpm(e.target.value); clearPreset(); }} />}
                      to={<Input type="number" placeholder="a" value={endBpm} onChange={(e) => { setEndBpm(e.target.value); clearPreset(); }} />} />
                    <ArcField label="Energia" hint="0–100"
                      from={<Input type="number" min={0} max={100} placeholder="da" value={startEnergy} onChange={(e) => { setStartEnergy(e.target.value); clearPreset(); }} />}
                      to={<Input type="number" min={0} max={100} placeholder="a" value={endEnergy} onChange={(e) => { setEndEnergy(e.target.value); clearPreset(); }} />} />
                    <ArcField label="Mood"
                      from={<Input placeholder="es. dark" value={startMood} onChange={(e) => setStartMood(e.target.value)} />}
                      to={<Input placeholder="es. euphoric" value={endMood} onChange={(e) => setEndMood(e.target.value)} />} />
                  </div>
                </Section>

                <Section icon={<SlidersHorizontal size={13} className="text-faint" />} title="Vincoli">
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    <Field label="Strategia" hint={STRATEGIES.find((s) => s.value === strategy)?.desc}>
                      <Select value={strategy} onChange={(e) => { setStrategy(e.target.value); clearPreset(); }}>
                        {STRATEGIES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                      </Select>
                    </Field>
                    <Field label="Max per artista"><Input type="number" min={1} value={maxPerArtist} onChange={(e) => setMaxPerArtist(Number(e.target.value))} /></Field>
                    <Field label="Artisti seed">
                      <Input placeholder="es. Arca, Sega Bodega" value={seedArtists} onChange={(e) => setSeedArtists(e.target.value)} />
                    </Field>
                  </div>
                  <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
                    <Checkbox label="evita tracce corte" checked={avoidShort} onChange={setAvoidShort} />
                    <Checkbox label="solo brani posseduti" checked={ownedOnly} onChange={setOwnedOnly} />
                    {SOURCES.map((s) => (
                      <Checkbox key={s.value} label={`solo ${s.label}`} checked={sources.includes(s.value)} onChange={() => toggleSource(s.value)} />
                    ))}
                  </div>
                </Section>
              </div>
            </details>

            <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
              <span className="text-xs text-faint">
                Motore <span className="text-muted">{useAi ? "AI" : "algoritmico"}</span> · premi Genera o <kbd className="rounded-none border border-border px-1 text-muted">⌘⏎</kbd>
              </span>
              <Button onClick={generate} disabled={busy}>
                <Wand2 size={16} /> {busy ? "Generazione…" : "Genera"}
              </Button>
            </div>
          </div>
        </Card>
      </div>

      {busy && (
        <Card className="mb-6">
          <div className="p-5">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 font-medium"><Sparkles size={15} className="text-muted" /> {job?.phase ?? "Avvio…"}</span>
              <span className="tnum text-muted">{elapsed}s{job?.using_ai && elapsed > 8 ? " · di solito 1–2 min" : ""}</span>
            </div>
            <EqMeter value={null} className="h-6 w-full" />
            <p className="mt-2 text-xs text-faint">Appena pronto, il set si apre nel workbench.</p>
          </div>
        </Card>
      )}

      {error && <div className="mb-6"><Alert tone="danger">⚠ {error}</Alert></div>}

      {!busy && !error && (
        <EmptyState icon={<ListMusic size={28} />} title="Nessun set ancora">
          Imposta i vincoli o scrivi un prompt, poi premi <strong>Genera</strong> (o <kbd className="rounded-none border border-border px-1 text-xs">⌘⏎</kbd>). Il set si aprirà nel workbench con l&apos;arco di BPM ed energia e i consigli di mix.
        </EmptyState>
      )}
    </PageLayout>
  );
}
