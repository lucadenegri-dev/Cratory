"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ArrowLeft, Music4, ExternalLink, Pencil } from "lucide-react";
import { apiGet, fmtDuration, type Track } from "@/lib/api";
import { Badge, Alert } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { KeyBadge } from "@/components/key-badge";
import { TrackEditModal } from "@/components/track-edit-modal";

const SOURCE_TONE: Record<string, "info" | "warning" | "neutral"> = { spotify: "info", soundcloud: "warning", manual: "neutral" };

export default function LabelDetail({ params }: { params: Promise<{ label: string }> }) {
  const { label: raw } = use(params);
  const label = decodeURIComponent(raw);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Track | null>(null);

  useEffect(() => {
    apiGet<{ total: number; items: Track[] }>("/api/tracks", { label, limit: 500, sort: "artist" })
      .then((r) => setTracks(r.items))
      .catch((e) => setError(String(e.message ?? e)));
  }, [label]);

  const cell = "px-3 py-2.5";
  const totalDur = tracks.reduce((s, t) => s + (t.duration_seconds ?? 0), 0);
  const artistCount = new Set(tracks.map((t) => t.artist).filter(Boolean)).size;

  const marginalia = (
    <div className="space-y-2 border-t border-border pt-1 text-xs">
      <div className="flex justify-between gap-2"><span className="text-muted">Tracce</span><span className="tnum text-fg">{tracks.length}</span></div>
      <div className="flex justify-between gap-2"><span className="text-muted">Artisti</span><span className="tnum text-fg">{artistCount}</span></div>
      <div className="flex justify-between gap-2"><span className="text-muted">Durata</span><span className="tnum text-fg">{fmtDuration(totalDur)}</span></div>
    </div>
  );

  return (
    <PageLayout title="Etichetta" meta={label} marginaliaTitle="Statistiche" marginalia={marginalia}>
      <Link href="/labels" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Etichette</Link>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <div className="overflow-x-auto border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-faint">
              <th className={cell}>#</th>
              <th className={cell}>Title</th>
              <th className={cell}>Artist</th>
              <th className={cell}>Source</th>
              <th className={`${cell} tnum`}>BPM</th>
              <th className={cell}>Key</th>
              <th className={`${cell} tnum`}>Dur</th>
              <th className={cell}></th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((t, i) => (
              <tr key={t.id} className="border-b border-border/50 last:border-0 hover:bg-elevated/40">
                <td className={`${cell} tnum text-faint`}>{String(i + 1).padStart(2, "0")}</td>
                <td className={cell}>
                  <Link href={`/tracks/${t.id}`} className="flex items-center gap-2.5">
                    {t.album_art_url
                      ? <img src={t.album_art_url} alt="" className="h-8 w-8 shrink-0 rounded-none object-cover" />
                      : <span className="grid h-8 w-8 shrink-0 place-items-center rounded-none bg-elevated text-faint"><Music4 size={14} /></span>}
                    <span className="max-w-[16rem] truncate font-medium hover:text-fg-strong">{t.title ?? <span className="italic text-faint">senza titolo</span>}</span>
                  </Link>
                </td>
                <td className={`${cell} text-muted`}>{t.artist ?? "—"}</td>
                <td className={cell}><Badge tone={SOURCE_TONE[t.source_type] ?? "neutral"}>{t.source_type}</Badge></td>
                <td className={`${cell} tnum`}>{t.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum`}><KeyBadge camelot={t.camelot_key} /></td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(t.duration_seconds)}</td>
                <td className={cell}>
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => setEditing(t)} title="Modifica valori a mano" className="text-faint transition-colors hover:text-fg-strong"><Pencil size={14} /></button>
                    {t.spotify_url && <a href={t.spotify_url} target="_blank" rel="noreferrer" title="Apri su Spotify" className="text-faint hover:text-fg"><ExternalLink size={14} /></a>}
                  </div>
                </td>
              </tr>
            ))}
            {tracks.length === 0 && !error && <tr><td colSpan={8} className="px-3 py-10 text-center text-sm text-muted">Nessuna traccia.</td></tr>}
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
