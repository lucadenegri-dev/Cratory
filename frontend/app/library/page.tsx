"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { apiGet, fmtDuration, type Track } from "@/lib/api";

const SOURCES = ["", "spotify", "soundcloud", "local"];

export default function Library() {
  const [items, setItems] = useState<Track[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const [artist, setArtist] = useState("");
  const [title, setTitle] = useState("");
  const [source, setSource] = useState("");
  const [bpmMin, setBpmMin] = useState("");
  const [bpmMax, setBpmMax] = useState("");
  const [tonality, setTonality] = useState("");
  const [incomplete, setIncomplete] = useState(false);

  const load = useCallback(() => {
    apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      artist, title, source,
      bpm_min: bpmMin, bpm_max: bpmMax, tonality,
      incomplete_metadata: incomplete ? true : undefined,
      limit, offset,
    })
      .then((r) => { setItems(r.items); setTotal(r.total); setError(null); })
      .catch((e) => setError(String(e.message ?? e)));
  }, [artist, title, source, bpmMin, bpmMax, tonality, incomplete, offset]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load]);

  const input = "rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-sm w-28";

  return (
    <div>
      <h2 className="mb-4 text-2xl font-bold">Library <span className="text-base font-normal text-zinc-400">({total} tracce)</span></h2>

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <input className={input} placeholder="Artista" value={artist} onChange={(e) => { setArtist(e.target.value); setOffset(0); }} />
        <input className={input} placeholder="Titolo" value={title} onChange={(e) => { setTitle(e.target.value); setOffset(0); }} />
        <select className={input} value={source} onChange={(e) => { setSource(e.target.value); setOffset(0); }}>
          {SOURCES.map((s) => <option key={s} value={s}>{s || "Tutte le sorgenti"}</option>)}
        </select>
        <input className={input} placeholder="BPM min" type="number" value={bpmMin} onChange={(e) => { setBpmMin(e.target.value); setOffset(0); }} />
        <input className={input} placeholder="BPM max" type="number" value={bpmMax} onChange={(e) => { setBpmMax(e.target.value); setOffset(0); }} />
        <input className={input} placeholder="Key (es. 7A)" value={tonality} onChange={(e) => { setTonality(e.target.value); setOffset(0); }} />
        <label className="flex items-center gap-1 text-sm text-zinc-300">
          <input type="checkbox" checked={incomplete} onChange={(e) => { setIncomplete(e.target.checked); setOffset(0); }} />
          metadata incompleti
        </label>
      </div>

      {error && <p className="mb-4 rounded bg-red-950 p-3 text-sm text-red-300">⚠ {error}</p>}

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-700 text-left text-xs uppercase text-zinc-400">
            <th className="py-2 pr-2">Title</th><th className="pr-2">Artist</th><th className="pr-2">Source</th>
            <th className="pr-2">BPM</th><th className="pr-2">Key</th><th className="pr-2">Dur</th>
            <th className="pr-2">Year</th><th className="pr-2">Plays</th><th className="pr-2">Cues</th><th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr key={t.id} className="border-b border-zinc-800/60 hover:bg-zinc-900">
              <td className="py-1.5 pr-2">
                <span className="flex items-center gap-2">
                  {t.album_art_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={t.album_art_url} alt="" className="h-7 w-7 shrink-0 rounded object-cover" />
                  ) : (
                    <span className="h-7 w-7 shrink-0 rounded bg-zinc-800" />
                  )}
                  <Link href={`/tracks/${t.id}`} className="text-emerald-400 hover:underline">
                    {t.title ?? <span className="italic text-zinc-500">senza titolo ({t.source_type})</span>}
                  </Link>
                </span>
              </td>
              <td className="pr-2">{t.artist ?? <span className="text-zinc-600">—</span>}</td>
              <td className="pr-2 text-zinc-400">{t.source_type}</td>
              <td className="pr-2">{t.bpm?.toFixed(0) ?? "—"}</td>
              <td className="pr-2">{t.tonality ?? "—"}</td>
              <td className="pr-2">{fmtDuration(t.duration_seconds)}</td>
              <td className="pr-2">{t.year ?? "—"}</td>
              <td className="pr-2">{t.play_count}</td>
              <td className="pr-2">{t.cue_count || "—"}</td>
              <td>
                {t.spotify_url && (
                  <a href={t.spotify_url} target="_blank" rel="noreferrer" className="text-xs text-green-500 hover:underline">Spotify ↗</a>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-4 flex items-center gap-3 text-sm">
        <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}
          className="rounded bg-zinc-800 px-3 py-1 disabled:opacity-40">← Prec</button>
        <span className="text-zinc-400">{offset + 1}–{Math.min(offset + limit, total)} di {total}</span>
        <button disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}
          className="rounded bg-zinc-800 px-3 py-1 disabled:opacity-40">Succ →</button>
      </div>
    </div>
  );
}
