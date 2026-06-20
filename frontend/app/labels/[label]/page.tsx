"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ArrowLeft, Music4, ExternalLink, Pencil, Tags } from "lucide-react";
import { apiGet, fmtDuration, type Track } from "@/lib/api";
import { Card, Badge, Alert } from "@/components/ui";
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

  return (
    <div>
      <Link href="/labels" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Etichette</Link>

      <header className="mb-6">
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight"><Tags size={22} /> {label}</h1>
        <p className="mt-1 text-sm text-muted">{tracks.length} tracce · {fmtDuration(totalDur)}</p>
      </header>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <Card className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-faint">
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
            {tracks.map((t) => (
              <tr key={t.id} className="border-b border-border/50 last:border-0 hover:bg-elevated/40">
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
                <td className={`${cell} tnum`}><KeyBadge camelot={t.camelot_key} /></td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(t.duration_seconds)}</td>
                <td className={cell}>
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => setEditing(t)} title="Modifica valori a mano" className="text-faint transition-colors hover:text-primary"><Pencil size={14} /></button>
                    {t.spotify_url && <a href={t.spotify_url} target="_blank" rel="noreferrer" title="Apri su Spotify" className="text-faint hover:text-info"><ExternalLink size={14} /></a>}
                  </div>
                </td>
              </tr>
            ))}
            {tracks.length === 0 && !error && <tr><td colSpan={7} className="px-3 py-10 text-center text-sm text-muted">Nessuna traccia.</td></tr>}
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
