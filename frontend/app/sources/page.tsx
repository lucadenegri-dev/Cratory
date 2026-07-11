"use client";

import { useCallback, useEffect, useState } from "react";
import { listSources, deleteSource, type ScanRoot } from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { AddSource } from "@/components/add-source";
import { SourcesTable } from "@/components/sources-table";
import { Alert, EmptyState } from "@/components/ui";
import { useT } from "@/lib/i18n";

export default function SourcesPage() {
  const t = useT();
  const { scan, startScan, refresh } = useJobs();
  const [roots, setRoots] = useState<ScanRoot[]>([]);
  const [offline, setOffline] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const load = useCallback(() => {
    listSources()
      .then((r) => { setRoots(r); setOffline(false); })
      .catch(() => setOffline(true));
  }, []);

  useEffect(() => { load(); }, [load]);
  // ricarica conteggi/last_scanned quando uno scan finisce
  useEffect(() => { if (scan.status === "done") load(); }, [scan.status, load]);

  const onScan = async () => {
    setActionError(null);
    try {
      await startScan();
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.sources.scanStartFailed);
    }
  };
  const onDelete = async (id: number) => {
    if (deletingId !== null) return;
    setActionError(null);
    setDeletingId(id);
    try {
      await deleteSource(id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.sources.rootRemoveFailed);
    } finally {
      setDeletingId(null);
      load();
    }
  };

  const r = scan.result;

  return (
    <PageLayout
      title="Sources"
      meta={t.sources.rootsCount(roots.length)}
      marginaliaTitle={t.sources.lastScan}
      marginalia={
        r ? (
          <div className="flex flex-col gap-1.5 text-xs">
            <Row k={t.sources.statFound} v={r.found} />
            <Row k={t.sources.statNew} v={`+${r.inserted}`} />
            <Row k={t.sources.statUpdated} v={r.updated} />
            <Row k={t.sources.statMoved} v={r.moved} />
            <Row k={t.sources.statMissing} v={r.missing} />
            <Row k={t.sources.statErrors} v={r.errors} danger={r.errors > 0} />
          </div>
        ) : (
          <p className="text-xs text-faint">{t.sources.noScanSession}</p>
        )
      }
      guide={<>
        <p>{t.sources.guideFolders}</p>
        <p>{t.sources.guideAddPre}<b className="text-fg">scan</b>{t.sources.guideAddPost}</p>
      </>}
    >
      <div className="flex flex-col gap-5">
        {offline && <Alert>{t.sources.offline(process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8010")}</Alert>}
        {actionError && <Alert>{actionError}</Alert>}
        <AddSource onAdded={load} />
        {roots.length === 0 && !offline ? (
          <EmptyState title={t.sources.emptyTitle}>{t.sources.emptyBody}</EmptyState>
        ) : (
          <SourcesTable roots={roots} onScan={onScan} onDelete={onDelete} deletingId={deletingId} />
        )}
      </div>
    </PageLayout>
  );
}

function Row({ k, v, danger }: { k: string; v: string | number; danger?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted">{k}</span>
      <span className={`tnum ${danger ? "text-danger" : "text-fg"}`}>{v}</span>
    </div>
  );
}
