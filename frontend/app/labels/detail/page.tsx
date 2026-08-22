"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Pencil, Shovel } from "lucide-react";
import { apiGet, fmtDuration, type Track } from "@/lib/api";
import { Alert, Input } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { KeyBadge } from "@/components/key-badge";
import { TrackCover } from "@/components/track-cover";
import { TrackStateIcons } from "@/components/track-state-icons";
import { TrackEditModal } from "@/components/track-edit-modal";
import { MiniBars, type MiniBarRow } from "@/components/dashboard/mini-bars";
import { useT } from "@/lib/i18n";
import { withFrom } from "@/lib/back-link";

export default function LabelDetail() {
  return <Suspense><LabelDetailInner /></Suspense>;
}

function LabelDetailInner() {
  const t = useT();
  // Niente ri-decodifica manuale: useSearchParams ha gia' decodificato una
  // volta, e una seconda passata corrompe le etichette con % e rompe quelle
  // con spazi (vedi tests/rotte-query-string.test.ts).
  const label = useSearchParams().get("label") ?? "";
  const [all, setAll] = useState<Track[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Track | null>(null);

  const [qTitle, setQTitle] = useState("");
  const [qArtist, setQArtist] = useState("");
  const [qGenre, setQGenre] = useState("");

  // Origine per il link indietro del dettaglio traccia. Non piu' usePathname():
  // con la label nella query (non nel path) `/labels/detail` da solo non
  // basta piu' a tornare qui. Si ricostruisce dalla label gia' letta sopra,
  // stesso principio di app/playlists/detail/page.tsx.
  const from = `/labels/detail?label=${encodeURIComponent(label)}`;

  useEffect(() => {
    apiGet<{ total: number; items: Track[] }>("/api/tracks", { label, limit: 500, sort: "artist" })
      .then((r) => setAll(r.items))
      .catch((e) => setError(String(e.message ?? e)));
  }, [label]);

  const tracks = useMemo(() => {
    const inc = (v: string | null, q: string) => !q || (v ?? "").toLowerCase().includes(q.toLowerCase());
    return all.filter((tr) => inc(tr.title, qTitle) && inc(tr.artist, qArtist) && inc(tr.genre, qGenre));
  }, [all, qTitle, qArtist, qGenre]);

  const cell = "px-3 py-2.5";
  const totalDur = tracks.reduce((s, tr) => s + (tr.duration_seconds ?? 0), 0);
  const artistCount = new Set(tracks.map((tr) => tr.artist).filter(Boolean)).size;

  const genreRows: MiniBarRow[] = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const tr of tracks) if (tr.genre) counts[tr.genre] = (counts[tr.genre] ?? 0) + 1;
    return Object.entries(counts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6)
      .map(([g, n]) => ({ label: g, value: n, href: `/library?genre=${encodeURIComponent(g)}` }));
  }, [tracks]);

  const marginalia = (
    <div className="space-y-4">
      <div className="space-y-2">
        <Input className="h-9" placeholder={t.library.filterTitlePlaceholder} value={qTitle} onChange={(e) => setQTitle(e.target.value)} />
        <Input className="h-9" placeholder={t.library.filterArtistPlaceholder} value={qArtist} onChange={(e) => setQArtist(e.target.value)} />
        <Input className="h-9" placeholder={t.library.filterGenrePlaceholder} value={qGenre} onChange={(e) => setQGenre(e.target.value)} />
      </div>
      <div className="space-y-2 border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2"><span className="text-muted">{t.labels.detail.statTracks}</span><span className="tnum text-fg">{tracks.length}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">{t.labels.detail.statArtists}</span><span className="tnum text-fg">{artistCount}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">{t.labels.detail.statDuration}</span><span className="tnum text-fg">{fmtDuration(totalDur)}</span></div>
      </div>
      {genreRows.length > 0 && (
        <div className="border-t border-border pt-4">
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.labels.detail.genresHeading}</div>
          <MiniBars rows={genreRows} />
        </div>
      )}
    </div>
  );

  return (
    <PageLayout title={t.labels.detail.pageTitle} meta={label} marginaliaTitle={t.labels.detail.marginaliaTitle} marginalia={marginalia}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <Link href="/labels" className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> {t.labels.detail.backLink}</Link>
        <Link
          href={`/discovery?seed=label&value=${encodeURIComponent(label)}`}
          className="inline-flex items-center gap-1.5 border border-border px-3 py-1.5 text-sm text-muted transition-colors hover:border-fg/40 hover:text-fg"
        >
          <Shovel size={14} /> {t.labels.detail.digThisLabel}
        </Link>
      </div>

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
              <th className={`${cell} tnum`}>{t.labels.detail.colDuration}</th>
              <th className={cell}>{t.labels.detail.colStatus}</th>
              <th className={cell}></th>
            </tr>
          </thead>
          <tbody>
            {tracks.map((tr, i) => (
              <tr key={tr.id} className="border-b border-border/50 last:border-0 hover:bg-elevated/40">
                <td className={`${cell} tnum text-faint`}>{String(i + 1).padStart(2, "0")}</td>
                <td className={cell}>
                  <Link href={withFrom(`/tracks?id=${tr.id}`, from)} className="flex items-center gap-2.5">
                    <TrackCover track={tr} className="h-8 w-8" iconSize={14} />
                    <span className="max-w-[16rem] truncate font-medium hover:text-fg-strong">{tr.title ?? <span className="italic text-faint">{t.library.untitledTrack}</span>}</span>
                  </Link>
                </td>
                <td className={`${cell} text-muted`}>{tr.artist ?? "—"}</td>
                <td className={`${cell} tnum`}>{tr.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum`}><KeyBadge camelot={tr.camelot_key} /></td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(tr.duration_seconds)}</td>
                <td className={cell}><TrackStateIcons track={tr} context={tracks} /></td>
                <td className={cell}>
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => setEditing(tr)} title={t.library.editValuesTitle} className="text-faint transition-colors hover:text-fg-strong"><Pencil size={14} /></button>
                  </div>
                </td>
              </tr>
            ))}
            {tracks.length === 0 && !error && <tr><td colSpan={8} className="px-3 py-10 text-center text-sm text-muted">{t.library.emptyStatePrefix}</td></tr>}
          </tbody>
        </table>
      </div>

      <TrackEditModal
        track={editing}
        open={editing !== null}
        onClose={() => setEditing(null)}
        onSaved={(saved) => setAll((cur) => cur.map((x) => (x.id === saved.id ? saved : x)))}
      />
    </PageLayout>
  );
}
