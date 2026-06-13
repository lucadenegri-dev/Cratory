"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Sparkles, Wand2, Download, ListMusic, AlertTriangle, Lightbulb, Compass, Music4 } from "lucide-react";
import {
  apiGet, apiPost, exportSet, fmtDuration, trackLabel,
  type AiStatus, type GenStatus, type Setlist,
} from "@/lib/api";
import { Card, CardHeader, Button, Input, Textarea, Select, Field, Checkbox, Badge, Progress, Alert, EmptyState } from "@/components/ui";

const STRATEGIES = ["smooth", "progressive", "contrast", "experimental", "peak_time", "warm_up", "closing"];
const RISK_TONE = { low: "success", medium: "warning", high: "danger" } as const;

export default function SetBuilder() {
  const [duration, setDuration] = useState(45);
  const [startBpm, setStartBpm] = useState("");
  const [endBpm, setEndBpm] = useState("");
  const [seedArtists, setSeedArtists] = useState("");
  const [strategy, setStrategy] = useState("smooth");
  const [maxPerArtist, setMaxPerArtist] = useState(2);
  const [sources, setSources] = useState<string[]>([]);
  const [avoidShort, setAvoidShort] = useState(true);
  const [avoidOverplayed, setAvoidOverplayed] = useState(false);
  const [prompt, setPrompt] = useState("");
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [useAi, setUseAi] = useState(false);

  const [setlist, setSetlist] = useState<Setlist | null>(null);
  const [job, setJob] = useState<GenStatus | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [exported, setExported] = useState<string | null>(null);
  const [playlistUrl, setPlaylistUrl] = useState<string | null>(null);
  const [playlistBusy, setPlaylistBusy] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    apiGet<AiStatus>("/api/ai/status").then((s) => { setAiStatus(s); setUseAi(s.configured); }).catch(() => setAiStatus({ configured: false, model: null }));
    return stopAll;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const stopAll = useCallback(() => {
    if (pollRef.current) clearInterval(pollRef.current);
    if (timerRef.current) clearInterval(timerRef.current);
    pollRef.current = timerRef.current = null;
  }, []);

  const busy = job?.status === "running";

  function toggleSource(s: string) {
    setSources((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
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
        target_duration_minutes: duration,
        start_bpm: startBpm ? Number(startBpm) : null,
        end_bpm: endBpm ? Number(endBpm) : null,
        seed_artists: seedArtists.split(",").map((s) => s.trim()).filter(Boolean),
        strategy,
        max_tracks_per_artist: maxPerArtist,
        sources,
        avoid_short_tracks: avoidShort,
        avoid_overplayed: avoidOverplayed,
        prompt: prompt || null,
        use_ai: useAi,
      });
      setJob(started);
      startPolling();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }

  async function doExport(format: "text" | "csv") {
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
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="Durata (min)"><Input type="number" value={duration} onChange={(e) => setDuration(Number(e.target.value))} /></Field>
            <Field label="BPM iniziale"><Input type="number" placeholder="auto" value={startBpm} onChange={(e) => setStartBpm(e.target.value)} /></Field>
            <Field label="BPM finale"><Input type="number" placeholder="auto" value={endBpm} onChange={(e) => setEndBpm(e.target.value)} /></Field>
            <Field label="Strategia">
              <Select value={strategy} onChange={(e) => setStrategy(e.target.value)}>
                {STRATEGIES.map((s) => <option key={s}>{s}</option>)}
              </Select>
            </Field>
            <Field label="Artisti seed" hint="separati da virgola">
              <Input placeholder="es. Arca, Sega Bodega" value={seedArtists} onChange={(e) => setSeedArtists(e.target.value)} />
            </Field>
            <Field label="Max per artista"><Input type="number" min={1} value={maxPerArtist} onChange={(e) => setMaxPerArtist(Number(e.target.value))} /></Field>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-border pt-4">
            <span className="text-xs font-medium uppercase tracking-wide text-muted">Sorgenti</span>
            {["spotify", "soundcloud", "local"].map((s) => (
              <Checkbox key={s} label={s} checked={sources.includes(s)} onChange={() => toggleSource(s)} />
            ))}
            <span className="mx-1 h-4 w-px bg-border" />
            <Checkbox label="evita tracce corte" checked={avoidShort} onChange={setAvoidShort} />
            <Checkbox label="evita troppo suonate" checked={avoidOverplayed} onChange={setAvoidOverplayed} />
          </div>

          <div className="mt-4">
            <Field label="Prompt libero" hint={useAi ? "interpretato dall'AI Set Agent" : "attiva l'AI per interpretarlo, altrimenti viene solo salvato"}>
              <Textarea rows={2} placeholder="Parti morbido e atmosferico, poi vira più club senza diventare techno dritta troppo presto…"
                value={prompt} onChange={(e) => setPrompt(e.target.value)} />
            </Field>
          </div>

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
            <p className="mt-2 text-xs text-faint">AI non configurata — imposta <code className="rounded bg-elevated px-1">AI_API_KEY</code> in backend/.env (vedi <Link href="/settings" className="text-info hover:underline">Impostazioni</Link>).</p>
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
          Imposta i vincoli o scrivi un prompt, poi premi <strong>Genera</strong>. Il set apparirà qui con spiegazioni e warning tecnici.
        </EmptyState>
      )}
    </div>
  );
}

function SetResult({ setlist, onExport, onPlaylist, playlistBusy, playlistUrl, exported }: {
  setlist: Setlist; onExport: (f: "text" | "csv") => void; onPlaylist: () => void;
  playlistBusy: boolean; playlistUrl: string | null; exported: string | null;
}) {
  const v = setlist.validation ?? {};
  const lists: Array<[string, string[] | undefined, "warning" | "info" | "primary", React.ReactNode]> = [
    ["Warning di validazione", v.warnings, "warning", <AlertTriangle key="w" size={14} />],
    ["Punti critici", v.critical_points, "warning", <AlertTriangle key="c" size={14} />],
    ["Direzioni alternative", v.alternative_directions, "info", <Compass key="a" size={14} />],
    ["Cosa manca in libreria", v.missing_library_suggestions, "primary", <Lightbulb key="m" size={14} />],
  ];
  const shown = lists.filter(([, items]) => items && items.length > 0);

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
        subtitle={`${setlist.tracks.length} tracce · ${fmtDuration(setlist.total_duration_seconds)}`}
        action={
          <div className="flex shrink-0 gap-2">
            <Button variant="outline" size="sm" onClick={() => onExport("text")}><Download size={14} /> Testo</Button>
            <Button variant="outline" size="sm" onClick={() => onExport("csv")}>CSV</Button>
            <Button variant="outline" size="sm" onClick={onPlaylist} disabled={playlistBusy}>{playlistBusy ? "…" : "Playlist Spotify"}</Button>
          </div>
        }
      />
      <div className="space-y-4 p-5">
        {playlistUrl && <Alert tone="success">✓ Playlist creata: <a href={playlistUrl} target="_blank" rel="noreferrer" className="underline">{playlistUrl}</a></Alert>}
        {setlist.global_explanation && <p className="text-sm leading-relaxed text-muted">{setlist.global_explanation}</p>}

        {shown.length > 0 && (
          <div className="grid gap-3 sm:grid-cols-2">
            {shown.map(([title, items, tone, icon]) => (
              <div key={title} className="rounded-lg border border-border bg-bg p-3">
                <div className={`mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-${tone}`}>{icon} {title}</div>
                <ul className="space-y-1 text-sm text-muted">
                  {items!.map((it, i) => <li key={i} className="flex gap-1.5"><span className="text-faint">·</span>{it}</li>)}
                </ul>
              </div>
            ))}
          </div>
        )}

        <ol className="space-y-1.5">
          {setlist.tracks.map((st) => (
            <li key={st.position} className="flex gap-3 rounded-lg border border-border bg-bg p-3">
              <span className="tnum w-5 pt-0.5 text-right text-sm text-faint">{st.position}</span>
              {st.track.album_art_url
                ? <img src={st.track.album_art_url} alt="" className="h-10 w-10 shrink-0 rounded object-cover" />
                : <span className="grid h-10 w-10 shrink-0 place-items-center rounded bg-elevated text-faint"><Music4 size={16} /></span>}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <Link href={`/tracks/${st.track.id}`} className="truncate font-medium hover:text-primary">{trackLabel(st.track)}</Link>
                  <span className="tnum shrink-0 text-xs text-faint">{st.track.bpm?.toFixed(0) ?? "—"} BPM · {st.track.tonality ?? "?"} · {fmtDuration(st.track.duration_seconds)}</span>
                  {st.risk_level && (
                    <Badge tone={RISK_TONE[st.risk_level as keyof typeof RISK_TONE] ?? "neutral"} className="ml-auto">
                      {st.risk_level}{st.transition_score != null && ` · ${st.transition_score.toFixed(0)}`}
                    </Badge>
                  )}
                </div>
                {st.ai_reason && <p className="mt-1 text-xs text-primary/85">🎧 {st.ai_reason}</p>}
                {st.transition_reason && <p className="mt-0.5 text-xs text-faint">{st.transition_reason}</p>}
              </div>
            </li>
          ))}
        </ol>

        {exported && <pre className="max-h-72 overflow-auto rounded-lg border border-border bg-bg p-3 text-xs text-muted">{exported}</pre>}
      </div>
    </Card>
  );
}
