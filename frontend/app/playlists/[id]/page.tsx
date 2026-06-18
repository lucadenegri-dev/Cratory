"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft, Music4, ExternalLink, AlertTriangle, Info, Trash2, Sparkles, Compass, Pencil,
} from "lucide-react";
import {
  getPlaylist, playlistTracks, playlistGaps, deletePlaylist, fmtDuration,
  type Playlist, type Track, type GapAnalysis,
} from "@/lib/api";
import { Card, CardHeader, Badge, Alert, Button, Spinner } from "@/components/ui";
import { TrackEditModal } from "@/components/track-edit-modal";

const SOURCE_TONE: Record<string, "info" | "warning" | "neutral"> = { spotify: "info", soundcloud: "warning", manual: "neutral" };
const STATUS_TONE: Record<string, "success" | "info" | "warning" | "neutral"> = {
  ready_for_set: "success", enriched: "info", imported: "neutral", missing_features: "warning", low_confidence: "warning",
};

export default function PlaylistDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const pid = Number(id);
  const router = useRouter();
  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [gaps, setGaps] = useState<GapAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [editing, setEditing] = useState<Track | null>(null);

  useEffect(() => {
    getPlaylist(pid).then(setPlaylist).catch((e) => setError(String(e.message ?? e)));
    playlistTracks(pid).then(setTracks).catch(() => {});
    playlistGaps(pid).then(setGaps).catch(() => {});
  }, [pid]);

  const doDelete = async () => {
    if (!playlist) return;
    if (!window.confirm(`Rimuovere "${playlist.name}" e le sue ${playlist.track_count} tracce? Non si può annullare.`)) return;
    setDeleting(true);
    try {
      await deletePlaylist(pid);
      router.push("/playlists");
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setDeleting(false);
    }
  };

  if (error) return <div><Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Playlist</Link><Alert tone="danger">⚠ {error}</Alert></div>;
  if (!playlist) return <p className="text-muted">Caricamento…</p>;

  const ready = tracks.filter((t) => t.status === "ready_for_set").length;
  const totalDur = tracks.reduce((s, t) => s + (t.duration_seconds ?? 0), 0);
  const cell = "px-3 py-2.5";

  return (
    <div>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Playlist</Link>

      <div className="mb-6 flex flex-wrap items-start gap-4">
        {playlist.artwork_url
          ? <img src={playlist.artwork_url} alt="" className="h-24 w-24 rounded-xl object-cover" />
          : <span className="grid h-24 w-24 place-items-center rounded-xl bg-surface-2 text-faint"><Music4 size={30} /></span>}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{playlist.name}</h1>
            <Badge tone="neutral">{playlist.platform}</Badge>
            {playlist.kind === "liked" && <Badge tone="info">liked</Badge>}
          </div>
          <p className="mt-1 text-sm text-muted">{playlist.track_count} tracce · {ready} pronte per il set · {fmtDuration(totalDur)}{playlist.owner ? ` · ${playlist.owner}` : ""}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link href={`/set-builder?playlist=${pid}`}><Button size="sm"><Sparkles size={15} /> Costruisci un set</Button></Link>
            <Link href="/discovery"><Button size="sm" variant="outline"><Compass size={15} /> Scopri musica simile</Button></Link>
            {playlist.url && <a href={playlist.url} target="_blank" rel="noreferrer"><Button size="sm" variant="outline"><ExternalLink size={14} /> Spotify</Button></a>}
            <Button size="sm" variant="danger" onClick={doDelete} disabled={deleting}>{deleting ? <Spinner /> : <Trash2 size={15} />} Rimuovi</Button>
          </div>
        </div>
      </div>

      {gaps && gaps.gaps.length > 0 && (
        <Card className="mb-4">
          <CardHeader title="Buchi della playlist" subtitle="analisi deterministica per il DJ set" />
          <div className="grid gap-2 p-4">
            {gaps.gaps.map((g) => (
              <div key={g.gap_type} className="flex gap-2 text-sm">
                {g.severity === "warning"
                  ? <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />
                  : <Info size={15} className="mt-0.5 shrink-0 text-info" />}
                <div><span className="text-fg">{g.description}</span> <span className="text-muted">{g.suggestion}</span></div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-faint">
              <th className={`${cell} tnum`}>#</th>
              <th className={cell}>Title</th>
              <th className={cell}>Artist</th>
              <th className={cell}>Source</th>
              <th className={`${cell} tnum`}>BPM</th>
              <th className={cell}>Key</th>
              <th className={`${cell} tnum`}>Dur</th>
              <th className={cell}>Stato</th>
              <th className={cell}></th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((t, i) => (
              <tr key={t.id} className="border-b border-border/50 last:border-0 hover:bg-elevated/40">
                <td className={`${cell} tnum text-faint`}>{i + 1}</td>
                <td className={cell}>
                  <Link href={`/tracks/${t.id}`} className="flex items-center gap-2.5">
                    {t.album_art_url
                      ? <img src={t.album_art_url} alt="" className="h-8 w-8 shrink-0 rounded object-cover" />
                      : <span className="grid h-8 w-8 shrink-0 place-items-center rounded bg-elevated text-faint"><Music4 size={14} /></span>}
                    <span className="max-w-[16rem] truncate font-medium hover:text-primary">{t.title ?? <span className="italic text-faint">senza titolo</span>}</span>
                  </Link>
                </td>
                <td className={`${cell} text-muted`}>{t.artist ?? "—"}</td>
                <td className={cell}><Badge tone={SOURCE_TONE[t.source_type] ?? "neutral"}>{t.source_type}</Badge></td>
                <td className={`${cell} tnum`}>{t.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{t.camelot_key ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(t.duration_seconds)}</td>
                <td className={cell}><Badge tone={STATUS_TONE[t.status] ?? "neutral"}>{t.status}</Badge></td>
                <td className={cell}>
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => setEditing(t)} title="Modifica valori a mano" className="text-faint transition-colors hover:text-primary"><Pencil size={14} /></button>
                    {t.spotify_url && <a href={t.spotify_url} target="_blank" rel="noreferrer" title="Apri su Spotify" className="text-faint hover:text-info"><ExternalLink size={14} /></a>}
                  </div>
                </td>
              </tr>
            ))}
            {tracks.length === 0 && <tr><td colSpan={9} className="px-3 py-10 text-center text-sm text-muted">Nessuna traccia.</td></tr>}
          </tbody>
        </table>
      </Card>

      <TrackEditModal
        track={editing}
        open={editing !== null}
        onClose={() => setEditing(null)}
        onSaved={(t) => setTracks((cur) => cur.map((x) => (x.id === t.id ? t : x)))}
      />
    </div>
  );
}
