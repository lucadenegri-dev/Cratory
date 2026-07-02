"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Music4, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, ExternalLink, Pencil } from "lucide-react";
import { apiGet, fmtDuration, type Track } from "@/lib/api";
import { Input, Select, Checkbox, Alert, Badge, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { TrackEditModal } from "@/components/track-edit-modal";

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
  const [items, setItems] = useState<Track[] | null>(null);
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
  const [owned, setOwned] = useState(""); // "" = tutte | "true" = possedute | "false" = wishlist
  const [archived, setArchived] = useState(""); // "" = nascoste (default) | "true" = solo scartate
  const [sort, setSort] = useState("");
  const [order, setOrder] = useState<Order>("asc");
  const [editing, setEditing] = useState<Track | null>(null);

  const load = useCallback(() => {
    apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      artist, title, genre, source, status, bpm_min: bpmMin, bpm_max: bpmMax, key,
      incomplete_metadata: incomplete ? true : undefined,
      has_local_file: owned || undefined,
      archived: archived || undefined,
      sort: sort || undefined, order: sort ? order : undefined,
      limit, offset,
    })
      .then((r) => { setItems(r.items); setTotal(r.total); setError(null); })
      .catch((e) => setError(String(e.message ?? e)));
  }, [artist, title, genre, source, status, bpmMin, bpmMax, key, incomplete, owned, archived, sort, order, offset]);

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
      <Select className="h-9" value={archived} onChange={(e) => { setArchived(e.target.value); setOffset(0); }}>
        <option value="">Scartate: nascoste</option>
        <option value="true">Solo scartate</option>
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
              {th("Stato", "status")}
              <th className={cell}></th>
            </tr>
          </thead>
          <tbody>
            {(items ?? []).map((t, i) => (
              <tr key={t.id} className="border-b border-border/50 last:border-0 hover:bg-elevated/40">
                <td className={`${cell} tnum text-faint`}>{String(offset + i + 1).padStart(2, "0")}</td>
                <td className={cell}>
                  <Link href={`/tracks/${t.id}`} className="flex items-center gap-2.5">
                    {t.album_art_url
                      ? <img src={t.album_art_url} alt="" className="h-8 w-8 shrink-0 rounded-none object-cover" />
                      : <span className="grid h-8 w-8 shrink-0 place-items-center rounded-none bg-elevated text-faint"><Music4 size={14} /></span>}
                    <span className="max-w-[16rem] truncate font-medium hover:text-fg-strong">{t.title ?? <span className="italic text-faint">senza titolo</span>}</span>
                  </Link>
                </td>
                <td className={`${cell} text-muted`}>{t.artist ?? <span className="text-faint">—</span>}</td>
                <td className={`${cell} tnum`}>{t.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{t.camelot_key ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{t.energy ?? "—"}</td>
                <td className={`${cell} max-w-[10rem] truncate text-muted`}>{t.genre ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(t.duration_seconds)}</td>
                <td className={cell}>
                  <Badge tone={STATUS_TONE[t.status] ?? "neutral"}>{STATUS_LABEL[t.status] ?? t.status}</Badge>
                  {t.has_local_file && <Badge tone="success" className="ml-1">FILE</Badge>}
                  {t.archived && <Badge tone="warning" className="ml-1">SCARTATA</Badge>}
                </td>
                <td className={cell}>
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => setEditing(t)} title="Modifica valori a mano" className="text-faint transition-colors hover:text-fg-strong"><Pencil size={14} /></button>
                    {t.spotify_url && <a href={t.spotify_url} target="_blank" rel="noreferrer" title="Apri su Spotify" className="text-faint hover:text-fg"><ExternalLink size={14} /></a>}
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
