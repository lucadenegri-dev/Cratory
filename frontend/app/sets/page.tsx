"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Clock, ChevronRight, Download, ListMusic, Sparkles, Trash2 } from "lucide-react";
import {
  apiDelete, apiGet, errText, exportSet, fmtDate, fmtDuration,
  type SetlistSummary,
} from "@/lib/api";
import { Card, Badge, Alert, Button, EmptyState, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useT } from "@/lib/i18n";

export default function SetsPage() {
  // useSearchParams obbliga a un confine Suspense, come le altre pagine con query.
  return <Suspense><SetsInner /></Suspense>;
}

function SetsInner() {
  const t = useT();
  const router = useRouter();
  const playlistId = useSearchParams().get("playlist");
  const [sets, setSets] = useState<SetlistSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<SetlistSummary[]>("/api/sets").then(setSets).catch((e) => setError(errText(e)));
  }, []);

  /** Apre una bozza: niente si salva finche' non ci si mette dentro qualcosa
   *  (2026-09-19). Il set nasce alla prima traccia, dentro il banco. */
  const prepara = () =>
    router.push(playlistId ? `/sets/manual?playlist=${playlistId}` : "/sets/manual");

  /** Porta via un set del vecchio formato prima di cancellarlo: e' l'unica cosa
   *  che ancora si puo' fare con lui, e la riga lo promette. */
  const esporta = async (s: SetlistSummary) => {
    try {
      const testo = await exportSet(s.id, "text");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([testo], { type: "text/plain" }));
      a.download = `${s.name}.txt`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { setError(errText(e)); }
  };

  const elimina = async (id: number) => {
    try {
      await apiDelete(`/api/sets/${id}`);
      setSets((prev) => (prev ?? []).filter((s) => s.id !== id));
    } catch (e) { setError(errText(e)); }
  };

  const marginalia = (
    <div className="space-y-3">
      <Button variant="outline" size="sm" className="w-full" onClick={prepara}>
        <Sparkles size={15} /> {t.sets.manual.prepareButton}
      </Button>
      <div className="border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2">
          <span className="text-muted">{t.sets.savedSetsLabel}</span>
          <span className="tnum text-fg">{sets?.length ?? 0}</span>
        </div>
      </div>
    </div>
  );

  return (
    <PageLayout title={t.sets.pageTitle} meta={sets ? String(sets.length) : undefined}
      marginaliaTitle={t.sets.actionsTitle} marginalia={marginalia}>
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {sets === null && !error && <Loading />}

      {sets && sets.length === 0 && (
        <EmptyState icon={<ListMusic size={28} />} title={t.sets.emptyTitle}>
          {t.sets.emptyBody}
        </EmptyState>
      )}

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {sets?.map((s) => {
          const contenuto = (
            <Card className="h-full p-4 transition-colors hover:border-border-strong">
              <div className="mb-3 flex items-start justify-between gap-2">
                <h3 className="truncate font-medium leading-snug group-hover:text-fg-strong">{s.name}</h3>
                {/* Solo sui vecchi set generati: «a mano» e' l'unico modo di
                    prepararne uno, quindi dirlo su ognuno non distingue niente. */}
                {s.kind !== "manual" && <Badge>{t.sets.legacyBadge}</Badge>}
              </div>
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
                <span className="inline-flex items-center gap-1"><ListMusic size={13} /> {t.sets.trackCountLabel(s.track_count)}</span>
                {s.total_duration_seconds > 0 && (
                  <span className="tnum inline-flex items-center gap-1"><Clock size={13} /> {fmtDuration(s.total_duration_seconds)}</span>
                )}
              </div>
              {s.kind !== "manual" && (
                <p className="mt-2 text-xs text-faint">{t.sets.legacyHint}</p>
              )}
              <div className="mt-3 flex items-center justify-between text-xs text-faint">
                <span>{fmtDate(s.created_at)}</span>
                {s.kind === "manual" ? (
                  <ChevronRight size={15} className="transition-transform group-hover:translate-x-0.5 group-hover:text-fg" />
                ) : (
                  <span className="flex items-center gap-2">
                    <button type="button" title={t.sets.manual.exportButton}
                      onClick={() => void esporta(s)} className="text-muted hover:text-fg">
                      <Download size={15} />
                    </button>
                    <button type="button" title={t.common.delete}
                      onClick={() => void elimina(s.id)} className="text-muted hover:text-danger">
                      <Trash2 size={15} />
                    </button>
                  </span>
                )}
              </div>
            </Card>
          );
          // Un set generato non ha piu' una pagina dove aprirsi: e' una riga che
          // lo dice, non un link che porta a un 404 (deciso il 2026-09-19).
          return s.kind === "manual" ? (
            <Link key={s.id} href={`/sets/manual?id=${s.id}`} className="group">{contenuto}</Link>
          ) : (
            <div key={s.id}>{contenuto}</div>
          );
        })}
      </div>
    </PageLayout>
  );
}
