"use client";

import { useCallback, useEffect, useState } from "react";
import { listHistory, undoRun, fmtDate, type HistoryItem } from "@/lib/organize/api";
import { useJobs } from "@/components/organize/jobs-provider";
import { PageLayout } from "@/components/organize/page-layout";
import { Alert, EmptyState, Loading } from "@/components/organize/ui";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

export default function HistoryPage() {
  const t = useT();
  const { apply } = useJobs();
  const [runs, setRuns] = useState<HistoryItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(() => {
    listHistory()
      .then((r) => { setRuns(r); setOffline(false); })
      .catch(() => setOffline(true))
      .finally(() => setLoaded(true));
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
    catch (e) { setError(e instanceof Error ? e.message : t.organize.common.error); }
    finally { setBusyId(null); load(); }
  };

  const applied = runs.filter((r) => r.status === "applied").length;
  const undone = runs.filter((r) => r.status === "undone").length;

  return (
    <PageLayout
      title="History"
      meta={t.organize.history.runsCount(runs.length)}
      marginaliaTitle={t.organize.common.summary}
      marginalia={
        <div className="flex flex-col gap-4 text-xs">
          <div><div className="tnum text-2xl leading-none text-fg-strong">{applied}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-muted">{t.organize.history.statApplied}</div></div>
          <div><div className="tnum text-2xl leading-none text-fg-strong">{undone}</div><div className="mt-1 text-[10px] uppercase tracking-wider text-muted">{t.organize.history.statUndone}</div></div>
        </div>
      }
      guide={<>
        <p>{t.organize.history.guide1}</p>
        <p>{t.organize.history.guide2pre}<b className="text-fg">{t.organize.history.guide2undo}</b>{t.organize.history.guide2post}</p>
      </>}
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>{t.organize.common.backendOffline}</Alert>}
        {error && <Alert>{error}</Alert>}

        {!loaded ? (
          <Loading />
        ) : runs.length === 0 && !offline ? (
          <EmptyState title={t.organize.history.emptyTitle}>{t.organize.history.emptyBody}</EmptyState>
        ) : (
          <div className="overflow-x-auto border border-border">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="border-b border-border text-left text-[9px] uppercase tracking-wider text-faint">
                  <th className="px-3 py-2 font-normal">{t.organize.history.colRun}</th>
                  <th className="px-3 py-2 font-normal">{t.organize.history.colWhen}</th>
                  <th className="px-3 py-2 text-right font-normal">{t.organize.history.colOps}</th>
                  <th className="px-3 py-2 font-normal">{t.organize.history.colStatus}</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id} className="border-b border-surface-2 last:border-0">
                    <td className="px-3 py-2 text-fg-strong">#{r.id}</td>
                    <td className="px-3 py-2 text-muted">{fmtDate(r.created_at)}</td>
                    <td className="tnum px-3 py-2 text-right text-fg">
                      {r.kind === "manual_edit" ? t.organize.history.manualEdit : r.n_ops}
                    </td>
                    <td className="px-3 py-2">
                      <span className={cn("border border-border px-2 py-0.5 text-[9px] uppercase tracking-wider",
                        r.status === "applied" ? "text-ok" : "text-faint")}>
                        {r.status === "applied" ? t.organize.history.badgeApplied : t.organize.history.badgeUndone}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      {r.status === "applied" ? (
                        <button
                          disabled={busyId !== null}
                          onClick={() => onUndo(r.id)}
                          className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
                        >{t.organize.history.undo}</button>
                      ) : (
                        <span className="text-faint">{t.organize.common.empty}</span>
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
