"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Tags, RefreshCw, Users, Disc3 } from "lucide-react";
import { getLabels, backfillLabels, type LabelStats } from "@/lib/api";
import { Card, Button, Spinner, Alert, EmptyState, Badge } from "@/components/ui";

export default function Labels() {
  const [labels, setLabels] = useState<LabelStats[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [msgTone, setMsgTone] = useState<"success" | "warning">("success");
  const [remaining, setRemaining] = useState(0);

  const load = useCallback(() => {
    getLabels().then(setLabels).catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(load, [load]);

  const doBackfill = async () => {
    setBusy(true);
    setMsg(null);
    setError(null);
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
    }
  };

  const total = labels?.reduce((s, l) => s + l.track_count, 0) ?? 0;

  return (
    <div>
      <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight"><Tags size={22} /> Etichette</h1>
          <p className="mt-1 text-sm text-muted">
            {labels ? `${labels.length} etichette · ${total} tracce` : "Le etichette discografiche della tua libreria."}
          </p>
        </div>
        <Button size="sm" variant="outline" onClick={doBackfill} disabled={busy}>
          {busy ? <Spinner /> : <RefreshCw size={14} />} {remaining > 0 ? "Continua il recupero" : "Recupera etichette da Spotify"}
        </Button>
      </header>

      {msg && <div className="mb-4"><Alert tone={msgTone}>{msg}</Alert></div>}
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {labels === null && !error && <p className="text-muted">Caricamento…</p>}

      {labels && labels.length === 0 && (
        <EmptyState icon={<Tags size={28} />} title="Nessuna etichetta">
          Le tracce non hanno ancora l&apos;informazione sull&apos;etichetta. Premi
          <span className="font-medium text-fg"> “Recupera etichette da Spotify” </span>
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
                    <h2 className="min-w-0 truncate font-semibold text-fg" title={l.label}>{l.label}</h2>
                    <Badge tone="info">{l.track_count}</Badge>
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
    </div>
  );
}
