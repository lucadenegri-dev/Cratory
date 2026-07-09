"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Pencil } from "lucide-react";
import { apiGet, fmtDuration, type Track } from "@/lib/api";
import { Input, Select, Checkbox, Alert, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { TrackEditModal } from "@/components/track-edit-modal";
import { TrackCover } from "@/components/track-cover";
import { TrackStateIcons } from "@/components/track-state-icons";

const STATUS_OPTIONS: [string, string][] = [
  ["ready_for_set", "Pronte per il set"],
  ["imported", "Importate"],
];

type Order = "asc" | "desc";

export default function Library() {
  const [items, setItems] = useState<Track[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const limit = 50;

  const [artist, setArtist] = useState("");
  const [title, setTitle] = useState("");
  // Filtro genere pre-impostato via query param (es. link "Generi" dalla dashboard).
  const [genre, setGenre] = useState(
    typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("genre") ?? "" : "",
  );
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [bpmMin, setBpmMin] = useState("");
  const [bpmMax, setBpmMax] = useState("");
  const [key, setKey] = useState("");
  const [incomplete, setIncomplete] = useState(false);
  const [owned, setOwned] = useState(""); // "" = tutte | "true" = possedute | "false" = wishlist
  const [sort, setSort] = useState("");
  const [order, setOrder] = useState<Order>("asc");
  const [editing, setEditing] = useState<Track | null>(null);

  const load = useCallback(() => {
    apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      artist, title, genre, source, status, bpm_min: bpmMin, bpm_max: bpmMax, key,
      incomplete_metadata: incomplete ? true : undefined,
      has_local_file: owned || undefined,
      sort: sort || undefined, order: sort ? order : undefined,
      limit, offset,
    })
      .then((r) => { setItems(r.items); setTotal(r.total); setError(null); })
      .catch((e) => setError(String(e.message ?? e)));
  }, [artist, title, genre, source, status, bpmMin, bpmMax, key, incomplete, owned, sort, order, offset]);

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

  const filters = (
    <div className="space-y-2">
      <Input className="h-9" placeholder="Artista" value={artist} onChange={(e) => { setArtist(e.target.value); setOffset(0); }} />
      <Input className="h-9" placeholder="Titolo" value={title} onChange={(e) => { setTitle(e.target.value); setOffset(0); }} />
      <Input className="h-9" placeholder="Genere" value={genre} onChange={(e) => { setGenre(e.target.value); setOffset(0); }} />
      <Select className="h-9" value={source} onChange={(e) => { setSource(e.target.value); setOffset(0); }}>
        <option value="">Tutte le sorgenti</option>
        <option value="spotify">Spotify</option>
        <option value="manual">Manuale</option>
        <option value="local_files">File locali</option>
      </Select>
      <Select className="h-9" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
        <option value="">Tutti gli stati</option>
        {STATUS_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </Select>
      <Select className="h-9" value={owned} onChange={(e) => { setOwned(e.target.value); setOffset(0); }}>
        <option value="">Possesso: tutte</option>
        <option value="true">Solo posseduti</option>
        <option value="false">Wishlist (senza file)</option>
      </Select>
      <div className="grid grid-cols-2 gap-2">
        <Input className="h-9" type="number" placeholder="BPM min" value={bpmMin} onChange={(e) => { setBpmMin(e.target.value); setOffset(0); }} />
        <Input className="h-9" type="number" placeholder="BPM max" value={bpmMax} onChange={(e) => { setBpmMax(e.target.value); setOffset(0); }} />
      </div>
      <Input className="h-9" placeholder="Key (es. 7A)" value={key} onChange={(e) => { setKey(e.target.value); setOffset(0); }} />
      <div className="pt-1"><Checkbox label="solo dati incompleti" checked={incomplete} onChange={(v) => { setIncomplete(v); setOffset(0); }} /></div>
    </div>
  );

  return (
    <PageLayout title="Libreria" meta={`${total} TRACCE`} marginaliaTitle="Filtri" marginalia={filters}>
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <div className="border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-faint">
              <th className={cell}>#</th>
              {th("Title", "title")}
              {th("Artist", "artist")}
              {th("BPM", "bpm", true)}
              {th("Key", "key")}
              {th("Energy", "energy", true)}
              {th("Genere", "genre")}
              {th("Dur", "duration", true)}
              <th className={cell}>Stato</th>
              <th className={cell}></th>
            </tr>
          </thead>
          <tbody>
            {(items ?? []).map((t, i) => (
              <tr key={t.id} className="border-b border-border/50 last:border-0 hover:bg-elevated/40">
                <td className={`${cell} tnum text-faint`}>{String(offset + i + 1).padStart(2, "0")}</td>
                <td className={cell}>
                  <Link href={`/tracks/${t.id}`} className="flex items-center gap-2.5">
                    <TrackCover track={t} className="h-8 w-8" iconSize={14} />
                    <span className="max-w-[16rem] truncate font-medium hover:text-fg-strong">{t.title ?? <span className="italic text-faint">senza titolo</span>}</span>
                  </Link>
                </td>
                <td className={`${cell} text-muted`}>{t.artist ?? <span className="text-faint">—</span>}</td>
                <td className={`${cell} tnum`}>{t.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{t.camelot_key ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{t.energy ?? "—"}</td>
                <td className={`${cell} max-w-[10rem] truncate text-muted`}>{t.genre ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(t.duration_seconds)}</td>
                <td className={cell}><TrackStateIcons track={t} /></td>
                <td className={cell}>
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => setEditing(t)} title="Modifica valori a mano" className="text-faint transition-colors hover:text-fg-strong"><Pencil size={14} /></button>
                  </div>
                </td>
              </tr>
            ))}
            {items === null && (
              <tr><td colSpan={10} className="px-3"><Loading /></td></tr>
            )}
            {items?.length === 0 && (
              <tr><td colSpan={10} className="px-3 py-10 text-center text-sm text-muted">Nessuna traccia con questi filtri. <Link href="/playlists" className="text-fg underline-offset-4 hover:underline">Importa una playlist</Link> per iniziare.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between text-sm">
        <span className="text-muted">{total === 0 ? "0" : `${offset + 1}–${Math.min(offset + limit, total)}`} di {total}</span>
        <div className="flex gap-2">
          <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}
            className="inline-flex h-8 items-center gap-1 rounded-none border border-border-strong px-3 hover:bg-elevated disabled:opacity-40"><ChevronLeft size={15} /> Prec</button>
          <button disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}
            className="inline-flex h-8 items-center gap-1 rounded-none border border-border-strong px-3 hover:bg-elevated disabled:opacity-40">Succ <ChevronRight size={15} /></button>
        </div>
      </div>

      <TrackEditModal
        track={editing}
        open={editing !== null}
        onClose={() => setEditing(null)}
        onSaved={(t) => setItems((cur) => (cur ?? []).map((x) => (x.id === t.id ? t : x)))}
      />
    </PageLayout>
  );
}
