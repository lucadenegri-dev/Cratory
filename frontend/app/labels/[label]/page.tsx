"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Pencil } from "lucide-react";
import { apiGet, fmtDuration, type Track } from "@/lib/api";
import { Alert, Input } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { KeyBadge } from "@/components/key-badge";
import { TrackCover } from "@/components/track-cover";
import { TrackStateIcons } from "@/components/track-state-icons";
import { TrackEditModal } from "@/components/track-edit-modal";
import { MiniBars, type MiniBarRow } from "@/components/dashboard/mini-bars";

export default function LabelDetail({ params }: { params: Promise<{ label: string }> }) {
  const { label: raw } = use(params);
  const label = decodeURIComponent(raw);
  const [all, setAll] = useState<Track[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Track | null>(null);

  const [qTitle, setQTitle] = useState("");
  const [qArtist, setQArtist] = useState("");
  const [qGenre, setQGenre] = useState("");

  useEffect(() => {
    apiGet<{ total: number; items: Track[] }>("/api/tracks", { label, limit: 500, sort: "artist" })
      .then((r) => setAll(r.items))
      .catch((e) => setError(String(e.message ?? e)));
  }, [label]);

  const tracks = useMemo(() => {
    const inc = (v: string | null, q: string) => !q || (v ?? "").toLowerCase().includes(q.toLowerCase());
    return all.filter((t) => inc(t.title, qTitle) && inc(t.artist, qArtist) && inc(t.genre, qGenre));
  }, [all, qTitle, qArtist, qGenre]);

  const cell = "px-3 py-2.5";
  const totalDur = tracks.reduce((s, t) => s + (t.duration_seconds ?? 0), 0);
  const artistCount = new Set(tracks.map((t) => t.artist).filter(Boolean)).size;

  const genreRows: MiniBarRow[] = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const t of tracks) if (t.genre) counts[t.genre] = (counts[t.genre] ?? 0) + 1;
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([g, n]) => ({ label: g, value: n, href: `/library?genre=${encodeURIComponent(g)}` }));
  }, [tracks]);

  const marginalia = (
    <div className="space-y-4">
      <div className="space-y-2">
        <Input className="h-9" placeholder="Titolo" value={qTitle} onChange={(e) => setQTitle(e.target.value)} />
        <Input className="h-9" placeholder="Artista" value={qArtist} onChange={(e) => setQArtist(e.target.value)} />
        <Input className="h-9" placeholder="Genere" value={qGenre} onChange={(e) => setQGenre(e.target.value)} />
      </div>
      <div className="space-y-2 border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2"><span className="text-muted">Tracce</span><span className="tnum text-fg">{tracks.length}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">Artisti</span><span className="tnum text-fg">{artistCount}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">Durata</span><span className="tnum text-fg">{fmtDuration(totalDur)}</span></div>
      </div>
      {genreRows.length > 0 && (
        <div className="border-t border-border pt-4">
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">Generi</div>
          <MiniBars rows={genreRows} />
        </div>
      )}
    </div>
  );

  return (
    <PageLayout title="Etichetta" meta={label} marginaliaTitle="Filtra" marginalia={marginalia}>
      <Link href="/labels" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Etichette</Link>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <div className="overflow-x-auto border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-faint">
              <th className={cell}>#</th>
              <th className={cell}>Title</th>
              <th className={cell}>Artist</th>
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
                <td className={`${cell} tnum text-faint`}>{String(i + 1).padStart(2, "0")}</td>
                <td className={cell}>
                  <Link href={`/tracks/${t.id}`} className="flex items-center gap-2.5">
                    <TrackCover track={t} className="h-8 w-8" iconSize={14} />
                    <span className="max-w-[16rem] truncate font-medium hover:text-fg-strong">{t.title ?? <span className="italic text-faint">senza titolo</span>}</span>
                  </Link>
                </td>
                <td className={`${cell} text-muted`}>{t.artist ?? "—"}</td>
                <td className={`${cell} tnum`}>{t.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum`}><KeyBadge camelot={t.camelot_key} /></td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(t.duration_seconds)}</td>
                <td className={cell}><TrackStateIcons track={t} /></td>
                <td className={cell}>
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => setEditing(t)} title="Modifica valori a mano" className="text-faint transition-colors hover:text-fg-strong"><Pencil size={14} /></button>
                  </div>
                </td>
              </tr>
            ))}
            {tracks.length === 0 && !error && <tr><td colSpan={8} className="px-3 py-10 text-center text-sm text-muted">Nessuna traccia con questi filtri.</td></tr>}
          </tbody>
        </table>
      </div>

      <TrackEditModal
        track={editing}
        open={editing !== null}
        onClose={() => setEditing(null)}
        onSaved={(t) => setAll((cur) => cur.map((x) => (x.id === t.id ? t : x)))}
      />
    </PageLayout>
  );
}
