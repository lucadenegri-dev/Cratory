"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ArrowLeft, Radar, Music4, ExternalLink, Clock } from "lucide-react";
import { getDjSet, fmtDuration, fmtDate, type DjSetDetail } from "@/lib/api";
import { Card, CardHeader, Badge, Alert } from "@/components/ui";

export default function DjSetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [set, setSet] = useState<DjSetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getDjSet(Number(id)).then(setSet).catch((e) => setError(String(e.message ?? e)));
  }, [id]);

  if (error) return (
    <div>
      <Link href="/shazam" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Shazam</Link>
      <Alert tone="danger">⚠ {error}</Alert>
    </div>
  );
  if (!set) return <p className="text-muted">Caricamento…</p>;

  return (
    <div>
      <Link href="/shazam" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Shazam</Link>

      <div className="mb-6 flex flex-wrap items-start gap-4">
        {set.artwork_url
          ? <img src={set.artwork_url} alt="" className="h-24 w-24 rounded-xl object-cover" />
          : <span className="grid h-24 w-24 place-items-center rounded-xl bg-surface-2 text-faint"><Radar size={30} /></span>}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{set.title ?? "Set senza titolo"}</h1>
            {set.platform && <Badge tone="neutral">{set.platform}</Badge>}
          </div>
          <p className="mt-1 text-sm text-muted">
            {set.dj_name ?? "—"} · {set.identified_count} tracce identificate
            {set.duration_seconds ? ` · ${fmtDuration(set.duration_seconds)}` : ""} · {fmtDate(set.created_at)}
          </p>
          <a href={set.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 text-sm text-info hover:underline">
            <ExternalLink size={14} /> Sorgente
          </a>
        </div>
      </div>

      <Card>
        <CardHeader title="Tracce identificate" subtitle="Riconosciute via Shazam — non entrano in libreria" />
        {set.tracks.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-faint">
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
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded bg-elevated text-faint"><Music4 size={14} /></span>
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
    </div>
  );
}
