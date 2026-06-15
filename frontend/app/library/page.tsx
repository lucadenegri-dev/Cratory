"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Music4, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, ExternalLink } from "lucide-react";
import { apiGet, fmtDuration, type Track } from "@/lib/api";
import { Card, Input, Select, Checkbox, Alert, Badge } from "@/components/ui";

const SOURCE_TONE: Record<string, "info" | "warning" | "neutral"> = { spotify: "info", soundcloud: "warning", manual: "neutral" };
const STATUS_TONE: Record<string, "success" | "info" | "warning" | "neutral"> = {
  ready_for_set: "success", enriched: "info", imported: "neutral",
  missing_features: "warning", low_confidence: "warning",
};
const STATUS_LABEL: Record<string, string> = {
  ready_for_set: "ready", enriched: "enriched", imported: "imported",
  missing_features: "no feat", low_confidence: "low conf",
};
const STATUS_OPTIONS: [string, string][] = [
  ["ready_for_set", "Pronte per il set"],
  ["enriched", "Arricchite"],
  ["imported", "Importate"],
  ["missing_features", "Senza feature"],
  ["low_confidence", "Bassa confidenza"],
];

type Order = "asc" | "desc";

export default function Library() {
  const [items, setItems] = useState<Track[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const [artist, setArtist] = useState("");
  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState("");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [bpmMin, setBpmMin] = useState("");
  const [bpmMax, setBpmMax] = useState("");
  const [key, setKey] = useState("");
  const [incomplete, setIncomplete] = useState(false);
  const [sort, setSort] = useState("");
  const [order, setOrder] = useState<Order>("asc");

  const load = useCallback(() => {
    apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      artist, title, genre, source, status, bpm_min: bpmMin, bpm_max: bpmMax, key,
      incomplete_metadata: incomplete ? true : undefined,
      sort: sort || undefined, order: sort ? order : undefined,
      limit, offset,
    })
      .then((r) => { setItems(r.items); setTotal(r.total); setError(null); })
      .catch((e) => setError(String(e.message ?? e)));
  }, [artist, title, genre, source, status, bpmMin, bpmMax, key, incomplete, sort, order, offset]);

  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);

  const cell = "px-3 py-2.5";

  const toggleSort = (col: string) => {
    if (sort === col) setOrder(order === "asc" ? "desc" : "asc");
    else { setSort(col); setOrder("asc"); }
    setOffset(0);
  };

  const th = (label: string, col: string, numeric = false) => {
    const active = sort === col;
    return (
      <th
        onClick={() => toggleSort(col)}
        title="Ordina per questa colonna"
        className={`${cell} ${numeric ? "tnum " : ""}cursor-pointer select-none whitespace-nowrap transition-colors hover:text-fg ${active ? "text-fg" : ""}`}
      >
        <span className="inline-flex items-center gap-1">
          {label}
          {active && (order === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
        </span>
      </th>
    );
  };

  return (
    <div>
      <header className="mb-6 flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Libreria</h1>
          <p className="mt-1 text-sm text-muted">{total} tracce dalle tue playlist importate · filtra e ordina per colonna.</p>
        </div>
      </header>

      <Card className="mb-4">
        <div className="p-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            <Input className="h-9" placeholder="Artista" value={artist} onChange={(e) => { setArtist(e.target.value); setOffset(0); }} />
            <Input className="h-9" placeholder="Titolo" value={title} onChange={(e) => { setTitle(e.target.value); setOffset(0); }} />
            <Input className="h-9" placeholder="Genere" value={genre} onChange={(e) => { setGenre(e.target.value); setOffset(0); }} />
            <Select className="h-9" value={source} onChange={(e) => { setSource(e.target.value); setOffset(0); }}>
              <option value="">Tutte le sorgenti</option>
              <option value="spotify">Spotify</option>
              <option value="soundcloud">SoundCloud</option>
              <option value="manual">Manuale</option>
            </Select>
            <Select className="h-9" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
              <option value="">Tutti gli stati</option>
              {STATUS_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
            <Input className="h-9" type="number" placeholder="BPM min" value={bpmMin} onChange={(e) => { setBpmMin(e.target.value); setOffset(0); }} />
            <Input className="h-9" type="number" placeholder="BPM max" value={bpmMax} onChange={(e) => { setBpmMax(e.target.value); setOffset(0); }} />
            <Input className="h-9" placeholder="Key (es. 7A)" value={key} onChange={(e) => { setKey(e.target.value); setOffset(0); }} />
          </div>
          <div className="mt-2"><Checkbox label="solo dati incompleti (manca BPM/key o metadati)" checked={incomplete} onChange={(v) => { setIncomplete(v); setOffset(0); }} /></div>
        </div>
      </Card>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-faint">
              {th("Title", "title")}
              {th("Artist", "artist")}
              {th("Source", "source")}
              {th("BPM", "bpm", true)}
              {th("Key", "key")}
              {th("Energy", "energy", true)}
              {th("Genere", "genre")}
              {th("Dur", "duration", true)}
              {th("Stato", "status")}
              <th className={cell}></th>
            </tr>
          </thead>
          <tbody>
            {items.map((t) => (
              <tr key={t.id} className="border-b border-border/50 last:border-0 hover:bg-elevated/40">
                <td className={cell}>
                  <Link href={`/tracks/${t.id}`} className="flex items-center gap-2.5">
                    {t.album_art_url
                      ? <img src={t.album_art_url} alt="" className="h-8 w-8 shrink-0 rounded object-cover" />
                      : <span className="grid h-8 w-8 shrink-0 place-items-center rounded bg-elevated text-faint"><Music4 size={14} /></span>}
                    <span className="max-w-[16rem] truncate font-medium hover:text-primary">{t.title ?? <span className="italic text-faint">senza titolo</span>}</span>
                  </Link>
                </td>
                <td className={`${cell} text-muted`}>{t.artist ?? <span className="text-faint">—</span>}</td>
                <td className={cell}><Badge tone={SOURCE_TONE[t.source_type] ?? "neutral"}>{t.source_type}</Badge></td>
                <td className={`${cell} tnum`}>{t.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{t.camelot_key ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{t.energy ?? "—"}</td>
                <td className={`${cell} max-w-[10rem] truncate text-muted`}>{t.genre ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(t.duration_seconds)}</td>
                <td className={cell}><Badge tone={STATUS_TONE[t.status] ?? "neutral"}>{STATUS_LABEL[t.status] ?? t.status}</Badge></td>
                <td className={cell}>{t.spotify_url && <a href={t.spotify_url} target="_blank" rel="noreferrer" className="text-faint hover:text-info"><ExternalLink size={14} /></a>}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={10} className="px-3 py-10 text-center text-sm text-faint">Nessuna traccia con questi filtri. <Link href="/playlists" className="text-info hover:underline">Importa una playlist</Link> per iniziare.</td></tr>
            )}
          </tbody>
        </table>
      </Card>

      <div className="mt-4 flex items-center justify-between text-sm">
        <span className="text-muted">{total === 0 ? "0" : `${offset + 1}–${Math.min(offset + limit, total)}`} di {total}</span>
        <div className="flex gap-2">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}
            className="inline-flex h-8 items-center gap-1 rounded-lg border border-border-strong px-3 disabled:opacity-40 hover:bg-elevated"><ChevronLeft size={15} /> Prec</button>
          <button disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}
            className="inline-flex h-8 items-center gap-1 rounded-lg border border-border-strong px-3 disabled:opacity-40 hover:bg-elevated">Succ <ChevronRight size={15} /></button>
        </div>
      </div>
    </div>
  );
}
