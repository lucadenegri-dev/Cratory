"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ArrowLeft, Radar, Music4, ExternalLink, Clock, ListPlus } from "lucide-react";
import { getDjSet, importDjSetAsPlaylist, fmtDuration, fmtDate, type DjSetDetail } from "@/lib/api";
import { Card, CardHeader, Badge, Alert, Button, Spinner, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

export default function DjSetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [set, setSet] = useState<DjSetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [imported, setImported] = useState<{ id: number; created: number } | null>(null);

  useEffect(() => {
    getDjSet(Number(id)).then(setSet).catch((e) => setError(String(e.message ?? e)));
  }, [id]);

  const doImport = async () => {
    setImporting(true);
    setError(null);
    try {
      const r = await importDjSetAsPlaylist(Number(id));
      setImported({ id: r.playlist_id, created: r.created });
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setImporting(false);
    }
  };

  if (error) return (
    <PageLayout title="Identificazione">
      <Link href="/shazam" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Shazam</Link>
      <Alert tone="danger">⚠ {error}</Alert>
    </PageLayout>
  );
  if (!set) return <PageLayout title="Identificazione"><Loading /></PageLayout>;

  const importedPlaylistId = imported?.id ?? set.imported_playlist_id;

  const marginalia = (
    <div className="space-y-2 text-xs">
      <div className="flex justify-between gap-2"><span className="text-muted">DJ</span><span className="truncate text-fg">{set.dj_name ?? "—"}</span></div>
      <div className="flex justify-between gap-2"><span className="text-muted">Tracce</span><span className="tnum text-fg">{set.identified_count}</span></div>
      {set.duration_seconds ? <div className="flex justify-between gap-2"><span className="text-muted">Durata</span><span className="tnum text-fg">{fmtDuration(set.duration_seconds)}</span></div> : null}
      <a href={set.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 border-t border-border pt-3 text-fg underline-offset-4 hover:underline">
        <ExternalLink size={13} /> Sorgente
      </a>
      {set.tracks.length > 0 && (
        <div className="border-t border-border pt-3">
          {importedPlaylistId ? (
            <p className="text-[11px] text-muted">
              Importata come playlist{imported ? ` (${imported.created} tracce)` : ""} ·{" "}
              <Link href={`/playlists/${importedPlaylistId}`} className="text-fg underline-offset-4 hover:underline">apri</Link>
            </p>
          ) : (
            <Button size="sm" variant="outline" className="w-full" onClick={doImport} disabled={importing}>
              {importing ? <Spinner /> : <ListPlus size={14} />} Importa come playlist
            </Button>
          )}
        </div>
      )}
    </div>
  );

  return (
    <PageLayout title="Identificazione" meta={set.title ?? undefined} marginaliaTitle="Meta" marginalia={marginalia}>
      <Link href="/shazam" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Shazam</Link>

      <div className="mb-6 flex flex-wrap items-start gap-4">
        {set.artwork_url
          ? <img src={set.artwork_url} alt="" className="h-24 w-24 rounded-none object-cover" />
          : <span className="grid h-24 w-24 place-items-center rounded-none bg-surface-2 text-faint"><Radar size={30} /></span>}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{set.title ?? "Set senza titolo"}</h1>
            {set.platform && <Badge tone="neutral">{set.platform}</Badge>}
          </div>
          <p className="mt-1 text-sm text-muted">
            {set.dj_name ?? "—"} · {set.identified_count} tracce identificate
            {set.duration_seconds ? ` · ${fmtDuration(set.duration_seconds)}` : ""} · {fmtDate(set.created_at)}
          </p>
        </div>
      </div>

      <Card>
        <CardHeader title="Tracce identificate" subtitle="Riconosciute via Shazam" />
        {set.tracks.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted">
            Nessuna traccia riconosciuta {set.status === "error" ? "(identificazione fallita)" : "in questo set"}.
          </p>
        ) : (
          <ol className="divide-y divide-border">
            {set.tracks.map((t) => (
              <li key={t.position} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <span className="tnum w-5 shrink-0 text-right text-faint">{t.position}</span>
                <span className="tnum inline-flex w-14 shrink-0 items-center gap-1 text-xs text-faint">
                  <Clock size={12} /> {fmtDuration(t.start_offset_seconds)}
                </span>
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-none bg-elevated text-faint"><Music4 size={14} /></span>
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{t.artist ?? "?"}</span>
                  <span className="text-muted"> — {t.title ?? "?"}</span>
                </span>
                {t.isrc && <Badge tone="neutral" className="tnum shrink-0">{t.isrc}</Badge>}
              </li>
            ))}
          </ol>
        )}
      </Card>
    </PageLayout>
  );
}
