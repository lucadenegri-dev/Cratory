"use client";

import { useCallback, useEffect, useState } from "react";
import { listHistory, undoRun, fmtDate, type HistoryItem } from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { Alert, EmptyState } from "@/components/ui";
import { cn } from "@/lib/cn";

export default function HistoryPage() {
  const { apply } = useJobs();
  const [runs, setRuns] = useState<HistoryItem[]>([]);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    listHistory()
      .then((r) => { setRuns(r); setOffline(false); })
      .catch(() => setOffline(true));
  }, []);
  useEffect(() => { load(); }, [load]);
  // a fine apply compare una nuova run
  useEffect(() => { if (apply.status === "done") load(); }, [apply.status, load]);

  const onUndo = async (id: number) => {
    if (busyId !== null) return;
    setError(null); setBusyId(id);
    try {
      const res = await undoRun(id);
      if (res.error) setError(res.error);
    }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
    finally { setBusyId(null); load(); }
  };

  const applied = runs.filter((r) => r.status === "applied").length;
  const undone = runs.filter((r) => r.status === "undone").length;

  return (
    <PageLayout
      title="History"
      meta={`${runs.length} run`}
      marginaliaTitle="Riepilogo"
      marginalia={
        <div className="flex flex-col gap-4 text-xs">
          <div><div className="tnum text-2xl leading-none text-fg-strong">{applied}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-muted">applicate</div></div>
          <div><div className="tnum text-2xl leading-none text-fg-strong">{undone}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-muted">annullate</div></div>
        </div>
      }
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}
        {error && <Alert>{error}</Alert>}

        {runs.length === 0 && !offline ? (
          <EmptyState title="Nessuna run">Applica un piano da PLAN per vederlo qui.</EmptyState>
        ) : (
          <div className="overflow-x-auto border border-border">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-border text-left text-[9px] uppercase tracking-wider text-faint">
                  <th className="px-3 py-2 font-normal">Run</th>
                  <th className="px-3 py-2 font-normal">Quando</th>
                  <th className="px-3 py-2 text-right font-normal">Operazioni</th>
                  <th className="px-3 py-2 font-normal">Stato</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-b border-surface-2 last:border-0">
                    <td className="px-3 py-2 text-fg-strong">#{r.id}</td>
                    <td className="px-3 py-2 text-muted">{fmtDate(r.created_at)}</td>
                    <td className="tnum px-3 py-2 text-right text-fg">{r.n_ops}</td>
                    <td className="px-3 py-2">
                      <span className={cn("border border-border px-2 py-0.5 text-[9px] uppercase tracking-wider",
                        r.status === "applied" ? "text-ok" : "text-faint")}>
                        {r.status === "applied" ? "applicata" : "annullata"}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {r.status === "applied" ? (
                        <button
                          disabled={busyId !== null}
                          onClick={() => onUndo(r.id)}
                          className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
                        >↺ annulla</button>
                      ) : (
                        <span className="text-faint">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageLayout>
  );
}
