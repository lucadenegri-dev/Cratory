"use client";

import { useCallback, useEffect, useState } from "react";
import { listSources, deleteSource, type ScanRoot } from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { AddSource } from "@/components/add-source";
import { SourcesTable } from "@/components/sources-table";
import { Alert, EmptyState } from "@/components/ui";

export default function SourcesPage() {
  const { scan, startScan, refresh } = useJobs();
  const [roots, setRoots] = useState<ScanRoot[]>([]);
  const [offline, setOffline] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

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
      setActionError(e instanceof Error ? e.message : "Impossibile avviare lo scan");
    }
  };
  const onDelete = async (id: number) => {
    setActionError(null);
    try {
      await deleteSource(id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Impossibile rimuovere la radice");
    } finally {
      load();
    }
  };

  const r = scan.result;

  return (
    <PageLayout
      title="Sources"
      meta={`${roots.length} radici`}
      marginaliaTitle="Ultimo scan"
      marginalia={
        r ? (
          <div className="flex flex-col gap-1.5 text-xs">
            <Row k="trovati" v={r.found} />
            <Row k="nuovi" v={`+${r.inserted}`} />
            <Row k="aggiornati" v={r.updated} />
            <Row k="spostati" v={r.moved} />
            <Row k="mancanti" v={r.missing} />
            <Row k="errori" v={r.errors} danger={r.errors > 0} />
          </div>
        ) : (
          <p className="text-xs text-faint">Nessuno scan in questa sessione.</p>
        )
      }
    >
      <div className="flex flex-col gap-5">
        {offline && <Alert>Backend non raggiungibile su {process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8010"}. Avvia il server FastAPI.</Alert>}
        {actionError && <Alert>{actionError}</Alert>}
        <AddSource onAdded={load} />
        {roots.length === 0 && !offline ? (
          <EmptyState title="Nessuna radice">Aggiungi una cartella di musica per iniziare.</EmptyState>
        ) : (
          <SourcesTable roots={roots} onScan={onScan} onDelete={onDelete} />
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
