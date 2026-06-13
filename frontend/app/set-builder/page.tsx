"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiGet, apiPost, exportSet, fmtDuration, trackLabel, type AiStatus, type Setlist } from "@/lib/api";

const STRATEGIES = ["smooth", "progressive", "contrast", "experimental", "peak_time", "warm_up", "closing"];
const RISK_STYLE: Record<string, string> = {
  low: "bg-emerald-900 text-emerald-300",
  medium: "bg-amber-900 text-amber-300",
  high: "bg-red-950 text-red-300",
};

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

  useEffect(() => {
    apiGet<AiStatus>("/api/ai/status")
      .then((s) => { setAiStatus(s); setUseAi(s.configured); })
      .catch(() => setAiStatus({ configured: false, model: null }));
  }, []);

  const [setlist, setSetlist] = useState<Setlist | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [exported, setExported] = useState<string | null>(null);
  const [playlistUrl, setPlaylistUrl] = useState<string | null>(null);
  const [playlistBusy, setPlaylistBusy] = useState(false);

  function toggleSource(s: string) {
    setSources((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]));
  }

  async function generate() {
    setLoading(true);
    setError(null);
    setExported(null);
    setPlaylistUrl(null);
    try {
      const result = await apiPost<Setlist>("/api/sets/generate", {
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
      setSetlist(result);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setLoading(false);
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
      const r = await apiPost<{ playlist_url: string; tracks_added: number }>(
        "/api/spotify/create-playlist", { setlist_id: setlist.id });
      setPlaylistUrl(r.playlist_url);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setPlaylistBusy(false);
    }
  }

  const input = "rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm";

  return (
    <div className="max-w-5xl">
      <h2 className="mb-4 text-2xl font-bold">Set Builder</h2>

      <div className="mb-6 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <div className="grid gap-3 sm:grid-cols-3">
          <label className="text-sm">Durata target (min)
            <input type="number" className={`${input} mt-1 w-full`} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
          </label>
          <label className="text-sm">BPM iniziale
            <input type="number" className={`${input} mt-1 w-full`} placeholder="auto" value={startBpm} onChange={(e) => setStartBpm(e.target.value)} />
          </label>
          <label className="text-sm">BPM finale
            <input type="number" className={`${input} mt-1 w-full`} placeholder="auto" value={endBpm} onChange={(e) => setEndBpm(e.target.value)} />
          </label>
          <label className="text-sm">Strategia
            <select className={`${input} mt-1 w-full`} value={strategy} onChange={(e) => setStrategy(e.target.value)}>
              {STRATEGIES.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <label className="text-sm">Artisti seed (separati da virgola)
            <input className={`${input} mt-1 w-full`} placeholder="es. Arca, Sega Bodega" value={seedArtists} onChange={(e) => setSeedArtists(e.target.value)} />
          </label>
          <label className="text-sm">Max tracce per artista
            <input type="number" min={1} className={`${input} mt-1 w-full`} value={maxPerArtist} onChange={(e) => setMaxPerArtist(Number(e.target.value))} />
          </label>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
          <span className="text-zinc-400">Sorgenti:</span>
          {["spotify", "soundcloud", "local"].map((s) => (
            <label key={s} className="flex items-center gap-1">
              <input type="checkbox" checked={sources.includes(s)} onChange={() => toggleSource(s)} /> {s}
            </label>
          ))}
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={avoidShort} onChange={(e) => setAvoidShort(e.target.checked)} /> evita tracce corte
          </label>
          <label className="flex items-center gap-1">
            <input type="checkbox" checked={avoidOverplayed} onChange={(e) => setAvoidOverplayed(e.target.checked)} /> evita tracce troppo suonate
          </label>
        </div>

        <label className="mt-3 block text-sm">
          Prompt libero {useAi
            ? <span className="text-emerald-500">(interpretato dall&apos;AI Set Agent)</span>
            : <span className="text-zinc-500">(salvato col set; attiva l&apos;AI per interpretarlo)</span>}
          <textarea className={`${input} mt-1 w-full`} rows={2}
            placeholder="Fammi un set da 45 minuti partendo da Arca, poi più club…" value={prompt} onChange={(e) => setPrompt(e.target.value)} />
        </label>

        <div className="mt-3 flex items-center gap-2 text-sm">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={useAi} disabled={!aiStatus?.configured}
              onChange={(e) => setUseAi(e.target.checked)} />
            <span className={aiStatus?.configured ? "" : "text-zinc-500"}>
              Usa l&apos;AI Set Agent {aiStatus?.model && <span className="text-zinc-500">({aiStatus.model})</span>}
            </span>
          </label>
          {!aiStatus?.configured && (
            <span className="text-xs text-zinc-500">
              — imposta <code className="rounded bg-zinc-800 px-1">AI_API_KEY</code> in backend/.env per abilitarla
            </span>
          )}
        </div>

        <button onClick={generate} disabled={loading}
          className="mt-4 rounded bg-emerald-600 px-5 py-2 font-semibold hover:bg-emerald-500 disabled:opacity-50">
          {loading ? "Generazione…" : useAi ? "Genera set con AI" : "Genera set"}
        </button>
      </div>

      {error && <p className="mb-4 rounded bg-red-950 p-3 text-sm text-red-300">⚠ {error}</p>}

      {setlist && (
        <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
          <div className="mb-2 flex items-center justify-between gap-4">
            <h3 className="flex items-center gap-2 text-lg font-semibold">
              {setlist.name}
              <span className={`rounded px-2 py-0.5 text-xs font-normal ${
                setlist.generated_by === "ai" ? "bg-emerald-900 text-emerald-300" : "bg-zinc-800 text-zinc-400"}`}>
                {setlist.generated_by === "ai" ? "AI" : "algoritmico"}
              </span>
            </h3>
            <div className="flex gap-2">
              <button onClick={() => doExport("text")} className="rounded bg-zinc-800 px-3 py-1 text-sm hover:bg-zinc-700">Export testo</button>
              <button onClick={() => doExport("csv")} className="rounded bg-zinc-800 px-3 py-1 text-sm hover:bg-zinc-700">Export CSV</button>
              <button onClick={createPlaylist} disabled={playlistBusy}
                className="rounded bg-green-700 px-3 py-1 text-sm hover:bg-green-600 disabled:opacity-50">
                {playlistBusy ? "Creazione…" : "Crea playlist Spotify"}
              </button>
            </div>
          </div>
          {playlistUrl && (
            <p className="mb-3 rounded bg-emerald-950 p-3 text-sm text-emerald-300">
              ✓ Playlist creata:{" "}
              <a href={playlistUrl} target="_blank" rel="noreferrer" className="underline">{playlistUrl}</a>
            </p>
          )}
          <p className="mb-4 text-sm text-zinc-400">{setlist.global_explanation}</p>
          <p className="mb-3 text-sm">Durata effettiva: <strong>{fmtDuration(setlist.total_duration_seconds)}</strong></p>

          {(() => {
            const v = setlist.validation ?? {};
            const blocks: [string, string[] | undefined, string][] = [
              ["⚠ Warning di validazione", v.warnings, "text-amber-400"],
              ["🔧 Correzioni automatiche", v.auto_fixes, "text-zinc-400"],
              ["⚡ Punti critici", v.critical_points, "text-amber-300"],
              ["↔ Direzioni alternative", v.alternative_directions, "text-zinc-300"],
              ["🧭 Cosa manca in libreria", v.missing_library_suggestions, "text-emerald-300"],
            ];
            const shown = blocks.filter(([, items]) => items && items.length > 0);
            if (shown.length === 0) return null;
            return (
              <div className="mb-4 grid gap-3 sm:grid-cols-2">
                {shown.map(([title, items, color]) => (
                  <div key={title} className="rounded border border-zinc-800 bg-zinc-950 p-3 text-sm">
                    <h4 className={`mb-1 font-medium ${color}`}>{title}</h4>
                    <ul className="list-disc space-y-0.5 pl-4 text-xs text-zinc-400">
                      {items!.map((it, i) => <li key={i}>{it}</li>)}
                    </ul>
                  </div>
                ))}
              </div>
            );
          })()}

          <ol className="space-y-2">
            {setlist.tracks.map((st) => (
              <li key={st.position} className="rounded border border-zinc-800 bg-zinc-950 p-3">
                <div className="flex items-center gap-3">
                  <span className="w-6 text-right font-mono text-zinc-500">{st.position}.</span>
                  <Link href={`/tracks/${st.track.id}`} className="font-medium text-emerald-400 hover:underline">
                    {trackLabel(st.track)}
                  </Link>
                  <span className="text-xs text-zinc-500">
                    {st.track.bpm?.toFixed(0)} BPM · {st.track.tonality ?? "?"} · {fmtDuration(st.track.duration_seconds)}
                  </span>
                  {st.risk_level && (
                    <span className={`ml-auto rounded px-2 py-0.5 text-xs ${RISK_STYLE[st.risk_level] ?? ""}`}>
                      {st.risk_level}{st.transition_score != null && ` · ${st.transition_score.toFixed(0)}`}
                    </span>
                  )}
                </div>
                {st.ai_reason && (
                  <p className="ml-9 mt-1 text-xs text-emerald-300/80">🎧 {st.ai_reason}</p>
                )}
                {st.transition_reason && (
                  <p className="ml-9 mt-1 text-xs text-zinc-500">{st.transition_reason}</p>
                )}
              </li>
            ))}
          </ol>

          {exported && (
            <pre className="mt-4 max-h-72 overflow-auto rounded bg-zinc-950 p-3 text-xs text-zinc-300">{exported}</pre>
          )}
        </div>
      )}
    </div>
  );
}
