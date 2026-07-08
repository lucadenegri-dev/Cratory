"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft, Music4, ExternalLink, AlertTriangle, Info, Trash2, Sparkles, Compass, Pencil,
  HardDrive, Archive, CircleCheck,
  RefreshCw, ChevronUp, ChevronDown, Download,
} from "lucide-react";
import {
  getPlaylist, playlistTracks, playlistGaps, deletePlaylist, syncPlaylist, fmtDuration,
  startPlaylistDownload,
  type Playlist, type Track, type GapAnalysis,
} from "@/lib/api";
import { Card, Badge, Alert, Button, Spinner, Input, Select, Checkbox, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { TrackCover } from "@/components/track-cover";
import { useJobs } from "@/components/jobs-provider";
import { TrackEditModal } from "@/components/track-edit-modal";
import { KeyBadge } from "@/components/key-badge";
import { SpotifyGlyph } from "@/components/spotify-glyph";

const SOURCE_TONE: Record<string, "info" | "warning" | "neutral"> = { spotify: "info", soundcloud: "warning", manual: "neutral" };
const STATUS_OPTIONS: [string, string][] = [
  ["ready_for_set", "Pronte per il set"],
  ["imported", "Importate"],
];

type Order = "asc" | "desc";

// Ordinamento Camelot: prima il numero (1..12), poi la lettera (A prima di B).
function camelotRank(key: string | null): number {
  const m = key ? /^\s*(\d{1,2})\s*([ABab])\s*$/.exec(key) : null;
  if (!m) return Number.POSITIVE_INFINITY;
  return Number(m[1]) * 2 + (m[2].toUpperCase() === "B" ? 1 : 0);
}

export default function PlaylistDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const pid = Number(id);
  const router = useRouter();
  const [downloading, setDownloading] = useState(false);
  const jobs = useJobs();
  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [gaps, setGaps] = useState<GapAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [editing, setEditing] = useState<Track | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);

  // Filtri (come in libreria) — applicati lato client sulla playlist (insieme limitato).
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

  const reload = useCallback(() => {
    playlistTracks(pid).then(setTracks).catch(() => {});
    playlistGaps(pid).then(setGaps).catch(() => {});
  }, [pid]);

  useEffect(() => {
    getPlaylist(pid).then(setPlaylist).catch((e) => setError(String(e.message ?? e)));
    reload();
  }, [pid, reload]);

  // Rank di inserimento STABILE: posizione cronologica per added_at crescente
  // (la traccia aggiunta per prima nella playlist Spotify = #1). Resta legato alla
  // traccia anche quando si ordina/filtra per un'altra colonna.
  const insertionRank = useMemo(() => {
    const ranked = [...tracks].sort((a, b) => {
      const aa = a.added_at, bb = b.added_at;
      if (aa && bb) return aa < bb ? -1 : aa > bb ? 1 : a.id - b.id;
      if (aa) return -1;
      if (bb) return 1;
      return a.id - b.id;
    });
    const map = new Map<number, number>();
    ranked.forEach((t, i) => map.set(t.id, i + 1));
    return map;
  }, [tracks]);

  const visible = useMemo(() => {
    const inc = (v: string | null, q: string) => (v ?? "").toLowerCase().includes(q.toLowerCase());
    let rows = tracks.filter((t) => {
      if (artist && !inc(t.artist, artist)) return false;
      if (title && !inc(t.title, title)) return false;
      if (genre && !inc(t.genre, genre)) return false;
      if (source && t.source_type !== source) return false;
      if (status && t.status !== status) return false;
      if (key && !inc(t.camelot_key, key)) return false;
      if (bpmMin && (t.bpm ?? -Infinity) < Number(bpmMin)) return false;
      if (bpmMax && (t.bpm ?? Infinity) > Number(bpmMax)) return false;
      if (incomplete && t.bpm != null && t.camelot_key != null && t.title != null && t.artist != null) return false;
      return true;
    });

    const dir = order === "asc" ? 1 : -1;
    const num = (v: number | null) => (v == null ? (order === "asc" ? Infinity : -Infinity) : v);
    const str = (v: string | null) => (v ?? "").toLowerCase();
    const getters: Record<string, (t: Track) => number | string> = {
      rank: (t) => insertionRank.get(t.id) ?? 0,
      title: (t) => str(t.title), artist: (t) => str(t.artist), source: (t) => t.source_type,
      bpm: (t) => num(t.bpm), key: (t) => camelotRank(t.camelot_key), energy: (t) => num(t.energy),
      genre: (t) => str(t.genre), duration: (t) => num(t.duration_seconds), status: (t) => t.status,
    };
    if (sort && getters[sort]) {
      const g = getters[sort];
      rows = [...rows].sort((a, b) => { const x = g(a), y = g(b); return x < y ? -dir : x > y ? dir : 0; });
    } else {
      // ordine di default = ordine di inserimento
      rows = [...rows].sort((a, b) => (insertionRank.get(a.id) ?? 0) - (insertionRank.get(b.id) ?? 0));
    }
    return rows;
  }, [tracks, artist, title, genre, source, status, key, bpmMin, bpmMax, incomplete, sort, order, insertionRank]);

  const toggleSort = (col: string) => {
    if (sort === col) setOrder(order === "asc" ? "desc" : "asc");
    else { setSort(col); setOrder("asc"); }
  };

  const doDelete = async () => {
    if (!playlist) return;
    if (!window.confirm(`Rimuovere "${playlist.name}"? I lead senza file su disco, non presenti in altre playlist né in un set, verranno cancellati. Non si può annullare.`)) return;
    setDeleting(true);
    try {
      await deletePlaylist(pid);
      router.push("/playlists");
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setDeleting(false);
    }
  };

  const doSync = async () => {
    setSyncing(true);
    setSyncMsg(null);
    try {
      const r = await syncPlaylist(pid);
      const parts = [`${r.created} nuove`, `${r.removed} rimosse (restano in libreria)`, `${r.total} totali`];
      setSyncMsg(parts.join(" · "));
      getPlaylist(pid).then(setPlaylist).catch(() => {});
      reload();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setSyncing(false);
    }
  };

  if (error) return (
    <PageLayout title="Playlist">
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Playlist</Link>
      <Alert tone="danger">⚠ {error}</Alert>
    </PageLayout>
  );
  if (!playlist) return <PageLayout title="Playlist"><Loading /></PageLayout>;

  const ready = tracks.filter((t) => t.status === "ready_for_set").length;
  const ownedCount = tracks.filter((t) => t.has_local_file).length;
  const missing = tracks.filter((t) => !t.has_local_file && !t.archived).length;
  const totalDur = tracks.reduce((s, t) => s + (t.duration_seconds ?? 0), 0);
  const cell = "px-3 py-2.5";
  const canSync = playlist.platform === "spotify" && (playlist.kind === "liked" || !!playlist.platform_playlist_id);

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

  const doDownloadMissing = async () => {
    setDownloading(true);
    try {
      await startPlaylistDownload(pid);
      jobs.refresh(); // si resta qui: il progresso vive nella barra job in basso
    } catch (e) {
      setError(`Download non avviato: ${String((e as Error).message ?? e)}`);
    } finally {
      setDownloading(false);
    }
  };

  const marginalia = (
    <div className="space-y-3">
      <Link href={`/set-builder?playlist=${pid}`} className="block"><Button size="sm" className="w-full"><Sparkles size={15} /> Costruisci un set</Button></Link>
      <Link href={`/playlists/${pid}/expand`} className="block"><Button size="sm" variant="outline" className="w-full"><Compass size={15} /> Scopri musica simile</Button></Link>
      {missing > 0 && (
        <Button size="sm" variant="outline" className="w-full" onClick={doDownloadMissing} disabled={downloading}>
          {downloading ? <Spinner /> : <Download size={15} />} Scarica mancanti ({missing})
        </Button>
      )}
      {canSync && <Button size="sm" variant="outline" className="w-full" onClick={doSync} disabled={syncing}>{syncing ? <Spinner /> : <RefreshCw size={14} />} Aggiorna da Spotify</Button>}
      {playlist.url && <a href={playlist.url} target="_blank" rel="noreferrer" className="block"><Button size="sm" variant="outline" className="w-full"><ExternalLink size={14} /> Spotify</Button></a>}
      <Button size="sm" variant="danger" className="w-full" onClick={doDelete} disabled={deleting}>{deleting ? <Spinner /> : <Trash2 size={15} />} Rimuovi</Button>
      <div className="space-y-2 border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2"><span className="text-muted">Tracce</span><span className="tnum text-fg">{playlist.track_count}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">Pronte</span><span className="tnum text-fg">{ready}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">Durata</span><span className="tnum text-fg">{fmtDuration(totalDur)}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">Owner</span><span className="truncate text-fg">{playlist.owner ?? "—"}</span></div>
      </div>
    </div>
  );

  return (
    <PageLayout title="Playlist" meta={playlist.name} marginaliaTitle="Dettagli" marginalia={marginalia}>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Playlist</Link>

      <div className="mb-6 flex flex-wrap items-start gap-4">
        {playlist.artwork_url
          ? <img src={playlist.artwork_url} alt="" className="h-24 w-24 rounded-none object-cover" />
          : <span className="grid h-24 w-24 place-items-center rounded-none bg-surface-2 text-faint"><Music4 size={30} /></span>}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{playlist.name}</h1>
            <Badge tone="neutral">{playlist.platform}</Badge>
            {playlist.kind === "liked" && <Badge tone="neutral">liked</Badge>}
          </div>
          <p className="mt-1 text-sm text-muted">{playlist.track_count} tracce · {ready} pronte per il set · possiedi {ownedCount} di {tracks.length} · {fmtDuration(totalDur)}{playlist.owner ? ` · ${playlist.owner}` : ""}</p>
        </div>
      </div>

      {syncMsg && <div className="mb-4"><Alert tone="info">Sincronizzato: {syncMsg}</Alert></div>}

      {gaps && gaps.gaps.length > 0 && (
        <details className="group mb-4 border border-border">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted transition-colors hover:text-fg [&::-webkit-details-marker]:hidden">
            <span>Tips · {gaps.gaps.length}</span>
            <ChevronDown size={15} className="text-faint transition-transform duration-200 group-open:rotate-180" />
          </summary>
          <div className="grid gap-2 border-t border-border p-4">
            {gaps.gaps.map((g) => (
              <div key={g.gap_type} className="flex gap-2 text-sm">
                {g.severity === "warning"
                  ? <AlertTriangle size={15} className="mt-0.5 shrink-0 text-muted" />
                  : <Info size={15} className="mt-0.5 shrink-0 text-muted" />}
                <div><span className="text-fg">{g.description}</span> <span className="text-muted">{g.suggestion}</span></div>
              </div>
            ))}
          </div>
        </details>
      )}

      <Card className="mb-4">
        <div className="p-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            <Input className="h-9" placeholder="Artista" value={artist} onChange={(e) => setArtist(e.target.value)} />
            <Input className="h-9" placeholder="Titolo" value={title} onChange={(e) => setTitle(e.target.value)} />
            <Input className="h-9" placeholder="Genere" value={genre} onChange={(e) => setGenre(e.target.value)} />
            <Select className="h-9" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">Tutte le sorgenti</option>
              <option value="spotify">Spotify</option>
              <option value="manual">Manuale</option>
            </Select>
            <Select className="h-9" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">Tutti gli stati</option>
              {STATUS_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
            <Input className="h-9" type="number" placeholder="BPM min" value={bpmMin} onChange={(e) => setBpmMin(e.target.value)} />
            <Input className="h-9" type="number" placeholder="BPM max" value={bpmMax} onChange={(e) => setBpmMax(e.target.value)} />
            <Input className="h-9" placeholder="Key (es. 7A)" value={key} onChange={(e) => setKey(e.target.value)} />
          </div>
          <div className="mt-2"><Checkbox label="solo dati incompleti (manca BPM/key o metadati)" checked={incomplete} onChange={setIncomplete} /></div>
        </div>
      </Card>

      <div className="overflow-x-auto border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-faint">
              {th("#", "rank", true)}
              {th("Title", "title")}
              {th("Artist", "artist")}
              {th("Source", "source")}
              {th("BPM", "bpm", true)}
              {th("Key", "key")}
              {th("Dur", "duration", true)}
              <th className={cell}>Stato</th>
              <th className={cell}></th>
            </tr>
          </thead>
          <tbody>
            {visible.map((t) => (
              <tr key={t.id} className="border-b border-border/50 last:border-0 hover:bg-elevated/40">
                <td className={`${cell} tnum text-faint`}>{insertionRank.get(t.id) ?? "—"}</td>
                <td className={cell}>
                  <Link href={`/tracks/${t.id}`} className="flex items-center gap-2.5">
                    <TrackCover track={t} className="h-8 w-8" iconSize={14} />
                    <span className="max-w-[16rem] truncate font-medium hover:text-fg-strong">{t.title ?? <span className="italic text-faint">senza titolo</span>}</span>
                  </Link>
                </td>
                <td className={`${cell} text-muted`}>{t.artist ?? "—"}</td>
                <td className={cell}><Badge tone={SOURCE_TONE[t.source_type] ?? "neutral"}>{t.source_type}</Badge></td>
                <td className={`${cell} tnum`}>{t.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum`}><KeyBadge camelot={t.camelot_key} /></td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(t.duration_seconds)}</td>
                <td className={cell}>
                  <div className="flex items-center gap-2 text-faint">
                    {t.status === "ready_for_set" && (
                      <span title="Pronta per il set (BPM + tonalità)"><CircleCheck size={14} className="text-fg-strong" /></span>
                    )}
                    {t.has_local_file && (
                      <span title="File in libreria (su disco)"><HardDrive size={14} className="text-fg-strong" /></span>
                    )}
                    {t.archived && (
                      <span title="Scartata (nell'archivio)"><Archive size={14} /></span>
                    )}
                    {t.spotify_url && (
                      <a href={t.spotify_url} target="_blank" rel="noreferrer" title="Apri su Spotify"
                         className="text-[#1DB954] transition-colors hover:text-[#1ed760]"><SpotifyGlyph size={14} /></a>
                    )}
                  </div>
                </td>
                <td className={cell}>
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => setEditing(t)} title="Modifica valori a mano" className="text-faint transition-colors hover:text-fg-strong"><Pencil size={14} /></button>
                  </div>
                </td>
              </tr>
            ))}
            {visible.length === 0 && <tr><td colSpan={9} className="px-3 py-10 text-center text-sm text-muted">Nessuna traccia con questi filtri.</td></tr>}
          </tbody>
        </table>
      </div>

      <TrackEditModal
        track={editing}
        open={editing !== null}
        onClose={() => setEditing(null)}
        onSaved={(t) => setTracks((cur) => cur.map((x) => (x.id === t.id ? t : x)))}
      />
    </PageLayout>
  );
}
