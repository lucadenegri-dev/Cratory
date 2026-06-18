"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Sparkles, Wand2, Download, ListMusic, Lightbulb, Music4,
  TrendingUp, SlidersHorizontal, ArrowRight, Sunrise, Flame, Sunset,
} from "lucide-react";
import {
  apiGet, apiPost, exportSet, fmtDuration, trackLabel,
  type AiStatus, type GenStatus, type Setlist, type SetlistTrack, type Playlist,
} from "@/lib/api";
import { Card, CardHeader, Button, Input, Textarea, Select, Field, Checkbox, Badge, Progress, Alert, EmptyState } from "@/components/ui";
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
const CLASS_TONE = { technically_safe: "success", good_reset: "info", creative_risk: "warning" } as const;

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
  const [duration, setDuration] = useState(45);
  const [startBpm, setStartBpm] = useState("");
  const [endBpm, setEndBpm] = useState("");
  const [seedArtists, setSeedArtists] = useState("");
  const [strategy, setStrategy] = useState("smooth");
  const [maxPerArtist, setMaxPerArtist] = useState(2);
  const [sources, setSources] = useState<string[]>([]);
  const [avoidShort, setAvoidShort] = useState(true);
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

  const [setlist, setSetlist] = useState<Setlist | null>(null);
  const [job, setJob] = useState<GenStatus | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [exported, setExported] = useState<string | null>(null);
  const [playlistUrl, setPlaylistUrl] = useState<string | null>(null);
  const [playlistBusy, setPlaylistBusy] = useState(false);

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
  }

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
          setSetlist(await apiGet<Setlist>(`/api/sets/${s.setlist_id}`));
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

  async function generate() {
    setError(null);
    setExported(null);
    setPlaylistUrl(null);
    setSetlist(null);
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
        prompt: prompt || null,
        use_ai: useAi,
        mode,
      });
      setJob(started);
      startPolling();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }

  async function doExport(format: "text" | "csv" | "markdown") {
    if (!setlist) return;
    setExported(await exportSet(setlist.id, format));
  }

  async function createPlaylist() {
    if (!setlist) return;
    setPlaylistBusy(true);
    setError(null);
    try {
      const r = await apiPost<{ playlist_url: string }>("/api/spotify/create-playlist", { setlist_id: setlist.id });
      setPlaylistUrl(r.playlist_url);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setPlaylistBusy(false);
    }
  }

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Set Builder</h1>
        <p className="mt-1 text-sm text-muted">Genera una scaletta dai vincoli, o descrivi a parole il set che vuoi e lascia ragionare l&apos;AI.</p>
      </header>

      <Card className="mb-6">
        <div className="p-5">
          <Section icon={<Music4 size={13} className="text-faint" />} title="Base">
            <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
              <Field label="Playlist di partenza" hint="il set nasce solo da queste tracce (con BPM/key). Vuoto = tutta la libreria">
                <Select value={playlistId} onChange={(e) => setPlaylistId(e.target.value)}>
                  <option value="">Tutta la libreria</option>
                  {playlists.map((p) => <option key={p.id} value={p.id}>{p.name} · {p.track_count}</option>)}
                </Select>
              </Field>
              <Field label="Durata (min)"><Input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></Field>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="text-xs text-faint">Preset rapidi:</span>
              {PRESETS.map((p) => {
                const Icon = p.icon;
                return (
                  <button key={p.label} type="button" onClick={() => applyPreset(p)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface px-3 py-1 text-xs font-medium text-muted transition-colors hover:border-border-strong hover:text-fg">
                    <Icon size={13} /> {p.label}
                  </button>
                );
              })}
            </div>
          </Section>

          <Section icon={<TrendingUp size={13} className="text-faint" />} title="Arco del set">
            <div className="grid gap-4 sm:grid-cols-3">
              <ArcField label="BPM" hint="vuoto = automatico"
                from={<Input type="number" placeholder="da" value={startBpm} onChange={(e) => setStartBpm(e.target.value)} />}
                to={<Input type="number" placeholder="a" value={endBpm} onChange={(e) => setEndBpm(e.target.value)} />} />
              <ArcField label="Energia" hint="0–100"
                from={<Input type="number" min={0} max={100} placeholder="da" value={startEnergy} onChange={(e) => setStartEnergy(e.target.value)} />}
                to={<Input type="number" min={0} max={100} placeholder="a" value={endEnergy} onChange={(e) => setEndEnergy(e.target.value)} />} />
              <ArcField label="Mood"
                from={<Input placeholder="es. dark" value={startMood} onChange={(e) => setStartMood(e.target.value)} />}
                to={<Input placeholder="es. euphoric" value={endMood} onChange={(e) => setEndMood(e.target.value)} />} />
            </div>
          </Section>

          <Section icon={<SlidersHorizontal size={13} className="text-faint" />} title="Vincoli">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Strategia" hint={STRATEGIES.find((s) => s.value === strategy)?.desc}>
                <Select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                  {STRATEGIES.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
                </Select>
              </Field>
              <Field label="Max per artista"><Input type="number" min={1} value={maxPerArtist} onChange={(e) => setMaxPerArtist(Number(e.target.value))} /></Field>
              <Field label="Artisti seed" hint="separati da virgola">
                <Input placeholder="es. Arca, Sega Bodega" value={seedArtists} onChange={(e) => setSeedArtists(e.target.value)} />
              </Field>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2">
              <span className="text-xs font-medium uppercase tracking-wide text-muted">Sorgenti</span>
              {SOURCES.map((s) => (
                <Checkbox key={s.value} label={s.label} checked={sources.includes(s.value)} onChange={() => toggleSource(s.value)} />
              ))}
              <span className="mx-1 h-4 w-px bg-border" />
              <Checkbox label="evita tracce corte" checked={avoidShort} onChange={setAvoidShort} />
            </div>
          </Section>

          <Section icon={<Sparkles size={13} className="text-faint" />} title="Indicazioni & AI">
            <Field label="Prompt libero" hint={useAi ? "interpretato dall'AI Set Agent" : "attiva l'AI per interpretarlo, altrimenti viene solo salvato"}>
              <Textarea rows={2} placeholder="Parti morbido e atmosferico, poi vira più club senza diventare techno dritta troppo presto…"
                value={prompt} onChange={(e) => setPrompt(e.target.value)} />
            </Field>
            {useAi && aiStatus?.configured && (
              <div className="mt-4 flex flex-wrap items-center gap-3">
                <span className="text-xs font-medium uppercase tracking-wide text-muted">Stile AI</span>
                <div className="inline-flex rounded-lg border border-border bg-surface p-1">
                  {(["technical", "creative"] as const).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setMode(m)}
                      className={cn(
                        "rounded-md px-3 py-1 text-sm font-medium transition-colors",
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
            )}
          </Section>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <Checkbox
              label={<span className="flex items-center gap-1.5"><Sparkles size={14} className={aiStatus?.configured ? "text-primary" : ""} /> Usa l&apos;AI Set Agent {aiStatus?.model && <span className="text-faint">· {aiStatus.model}</span>}</span>}
              checked={useAi} disabled={!aiStatus?.configured} onChange={setUseAi}
            />
            <Button onClick={generate} disabled={busy}>
              <Wand2 size={16} /> {busy ? "Generazione…" : useAi ? "Genera con AI" : "Genera set"}
            </Button>
          </div>
          {!aiStatus?.configured && (
            <p className="mt-2 text-xs text-muted">AI non configurata — imposta <code className="rounded bg-elevated px-1">AI_API_KEY</code> in backend/.env (vedi <Link href="/settings" className="text-info hover:underline">Impostazioni</Link>).</p>
          )}
        </div>
      </Card>

      {busy && (
        <Card className="mb-6">
          <div className="p-5">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 font-medium"><Sparkles size={15} className="text-primary" /> {job?.phase ?? "Avvio…"}</span>
              <span className="tnum text-muted">{elapsed}s{job?.using_ai && elapsed > 8 ? " · di solito 1–2 min" : ""}</span>
            </div>
            <Progress value={null} />
          </div>
        </Card>
      )}

      {error && <div className="mb-6"><Alert tone="danger">⚠ {error}</Alert></div>}

      {setlist && !busy && <SetResult setlist={setlist} onExport={doExport} onPlaylist={createPlaylist} playlistBusy={playlistBusy} playlistUrl={playlistUrl} exported={exported} />}

      {!setlist && !busy && !error && (
        <EmptyState icon={<ListMusic size={28} />} title="Nessun set ancora">
          Imposta i vincoli o scrivi un prompt, poi premi <strong>Genera</strong>. Il set apparirà qui con i consigli tecnici di mix.
        </EmptyState>
      )}
    </div>
  );
}

function SetResult({ setlist, onExport, onPlaylist, playlistBusy, playlistUrl, exported }: {
  setlist: Setlist; onExport: (f: "text" | "csv" | "markdown") => void; onPlaylist: () => void;
  playlistBusy: boolean; playlistUrl: string | null; exported: string | null;
}) {
  const improvements = setlist.validation?.missing_library_suggestions ?? [];
  const transitions = Math.max(0, setlist.tracks.length - 1);
  const safe = setlist.tracks.filter((st) => (st.transition_score ?? 0) >= 70).length;

  return (
    <Card>
      <CardHeader
        title={
          <span className="flex items-center gap-2">
            {setlist.name}
            <Badge tone={setlist.generated_by === "ai" ? "primary" : "neutral"}>
              {setlist.generated_by === "ai" ? <><Sparkles size={11} /> AI</> : "algoritmico"}
            </Badge>
          </span>
        }
        subtitle={`${setlist.tracks.length} tracce · ${fmtDuration(setlist.total_duration_seconds)}${transitions ? ` · ${safe}/${transitions} mix sicuri` : ""}`}
        action={
          <div className="flex shrink-0 gap-2">
            <Button variant="outline" size="sm" onClick={() => onExport("text")}><Download size={14} /> Testo</Button>
            <Button variant="outline" size="sm" onClick={() => onExport("csv")}>CSV</Button>
            <Button variant="outline" size="sm" onClick={() => onExport("markdown")}>MD</Button>
            <Button variant="outline" size="sm" onClick={onPlaylist} disabled={playlistBusy}>{playlistBusy ? "…" : "Playlist Spotify"}</Button>
          </div>
        }
      />
      <div className="space-y-4 p-5">
        {playlistUrl && <Alert tone="success">✓ Playlist creata: <a href={playlistUrl} target="_blank" rel="noreferrer" className="underline">{playlistUrl}</a></Alert>}

        {setlist.mixing_overview.length > 0 && (
          <div className="rounded-lg border border-border bg-bg p-3">
            <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-info"><SlidersHorizontal size={14} /> Come mixare il set</div>
            <ul className="space-y-1 text-sm text-muted">
              {setlist.mixing_overview.map((it, i) => <li key={i} className="flex gap-1.5"><span className="text-faint">·</span>{it}</li>)}
            </ul>
          </div>
        )}

        <ol className="space-y-1.5">
          {setlist.tracks.map((st) => <SetTrackRow key={st.position} st={st} />)}
        </ol>

        {improvements.length > 0 && (
          <div className="rounded-lg border border-border bg-bg p-3">
            <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-primary"><Lightbulb size={14} /> Come migliorare il tuo set</div>
            <ul className="space-y-1 text-sm text-muted">
              {improvements.map((it, i) => <li key={i} className="flex gap-1.5"><span className="text-faint">·</span>{it}</li>)}
            </ul>
          </div>
        )}

        {exported && <pre className="max-h-72 overflow-auto rounded-lg border border-border bg-bg p-3 text-xs text-muted">{exported}</pre>}
      </div>
    </Card>
  );
}

/** Riga di una traccia del set: ruolo, brano, dati tecnici e consiglio di mix deterministico. */
function SetTrackRow({ st }: { st: SetlistTrack }) {
  return (
    <li className="flex gap-3 rounded-lg border border-border bg-bg p-3">
      <span className="tnum w-5 pt-0.5 text-right text-sm text-faint">{st.position}</span>
      {st.track.album_art_url
        ? <img src={st.track.album_art_url} alt="" className="h-10 w-10 shrink-0 rounded object-cover" />
        : <span className="grid h-10 w-10 shrink-0 place-items-center rounded bg-elevated text-faint"><Music4 size={16} /></span>}
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          {st.role && <Badge tone="neutral">{st.role}</Badge>}
          <Link href={`/tracks/${st.track.id}`} className="truncate font-medium hover:text-primary">{trackLabel(st.track)}</Link>
          <span className="tnum shrink-0 text-xs text-faint">{st.track.bpm?.toFixed(0) ?? "—"} BPM · {st.track.camelot_key ?? "?"} · {fmtDuration(st.track.duration_seconds)}</span>
          {st.transition_class && (
            <Badge tone={CLASS_TONE[st.transition_class] ?? "neutral"} className="ml-auto">
              {st.transition_class_label ?? st.transition_class}
            </Badge>
          )}
        </div>
        {st.mix_tip
          ? <p className="mt-1 flex gap-1.5 text-xs text-muted"><span className="shrink-0 text-faint">↪</span>{st.mix_tip}</p>
          : <p className="mt-1 text-xs text-faint">apertura del set</p>}
      </div>
    </li>
  );
}
