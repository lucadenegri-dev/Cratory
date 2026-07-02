"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { RefreshCw, Users, Disc3 } from "lucide-react";
import { getLabels, backfillLabels, type LabelStats } from "@/lib/api";
import { Button, Spinner, Alert, EmptyState, Badge, Card, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";

export default function Labels() {
  const [labels, setLabels] = useState<LabelStats[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [msgTone, setMsgTone] = useState<"success" | "warning">("success");
  const [remaining, setRemaining] = useState(0);
  const { startClientJob, endClientJob } = useJobs();

  const load = useCallback(() => {
    getLabels().then(setLabels).catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(load, [load]);

  const doBackfill = async () => {
    setBusy(true);
    setMsg(null);
    setError(null);
    startClientJob("labels", "Scaricamento etichette");
    try {
      const r = await backfillLabels();
      setRemaining(r.remaining);
      const parts: string[] = [];
      parts.push(r.updated > 0 ? `${r.updated} tracce aggiornate con l'etichetta` : "Nessuna nuova etichetta in questo lotto");
      if (r.rate_limited) {
        parts.push("Spotify ha applicato un rate limit: riprova più tardi");
        setMsgTone("warning");
      } else if (r.remaining > 0) {
        parts.push(`${r.remaining} tracce ancora da controllare — premi di nuovo per continuare`);
        setMsgTone("warning");
      } else {
        setMsgTone("success");
      }
      setMsg(parts.join(" · "));
      load();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
      endClientJob("labels");
    }
  };

  const total = labels?.reduce((s, l) => s + l.track_count, 0) ?? 0;

  const marginalia = (
    <div className="space-y-3">
      <Button size="sm" variant="outline" className="w-full" onClick={doBackfill} disabled={busy}>
        {busy ? <Spinner /> : <RefreshCw size={14} />} {remaining > 0 ? "Continua il recupero" : "Recupera da Spotify"}
      </Button>
      {labels && (
        <div className="space-y-2 border-t border-border pt-4 text-xs">
          <div className="flex justify-between gap-2"><span className="text-muted">Etichette</span><span className="tnum text-fg">{labels.length}</span></div>
          <div className="flex justify-between gap-2"><span className="text-muted">Tracce</span><span className="tnum text-fg">{total}</span></div>
        </div>
      )}
    </div>
  );

  return (
    <PageLayout title="Etichette" meta={labels ? `${labels.length}` : undefined} marginaliaTitle="Totali" marginalia={marginalia}>
      {msg && <div className="mb-4"><Alert tone={msgTone === "warning" ? "warning" : "info"}>{msg}</Alert></div>}
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {labels === null && !error && <Loading />}

      {labels && labels.length === 0 && (
        <EmptyState icon={<Disc3 size={28} />} title="Nessuna etichetta">
          Le tracce non hanno ancora l&apos;informazione sull&apos;etichetta. Premi
          <span className="font-medium text-fg"> “Recupera da Spotify” </span>
          per leggerla dagli album.
        </EmptyState>
      )}

      {labels && labels.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {labels.map((l) => {
            const years = l.year_min ? (l.year_max && l.year_max !== l.year_min ? `${l.year_min}–${l.year_max}` : `${l.year_min}`) : null;
            return (
              <Link key={l.label} href={`/labels/${encodeURIComponent(l.label)}`}>
                <Card className="h-full p-4 transition-colors hover:bg-elevated/40">
                  <div className="flex items-start justify-between gap-2">
                    <h2 className="min-w-0 truncate font-semibold text-fg-strong" title={l.label}>{l.label}</h2>
                    <Badge tone="neutral">{l.track_count}</Badge>
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                    <span className="inline-flex items-center gap-1"><Disc3 size={13} /> {l.track_count} tracce</span>
                    <span className="inline-flex items-center gap-1"><Users size={13} /> {l.artist_count} artisti</span>
                    {years && <span>{years}</span>}
                  </div>
                  {l.genres.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1">
                      {l.genres.map((g) => <Badge key={g} tone="neutral">{g}</Badge>)}
                    </div>
                  )}
                </Card>
              </Link>
            );
          })}
        </div>
      )}
    </PageLayout>
  );
}
