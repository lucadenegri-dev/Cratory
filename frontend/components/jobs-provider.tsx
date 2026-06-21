"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { enrichmentJobStatus, shazamIdentifyStatus } from "@/lib/api";
import { Progress, Spinner } from "./ui";

type Job = { key: string; label: string; processed: number; total: number };

const JobsCtx = createContext<{ refresh: () => void }>({ refresh: () => {} });

/** Permette a una pagina di forzare un poll immediato dopo aver avviato un job. */
export function useJobs() {
  return useContext(JobsCtx);
}

/**
 * Poller globale dei job in background (arricchimento feature, identificazione
 * Shazam). Vive nello shell, quindi continua a girare anche cambiando pagina:
 * il progresso viene mostrato in una barra fissa in basso finché un job è attivo.
 */
export function JobsProvider({ children }: { children: ReactNode }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const alive = useRef(true);

  const pollOnce = useCallback(async () => {
    const next: Job[] = [];
    try {
      const e = await enrichmentJobStatus();
      if (e.status === "running") next.push({ key: "enrich", label: "Arricchimento feature", processed: e.processed, total: e.total });
    } catch { /* backend offline: ignora */ }
    try {
      const s = await shazamIdentifyStatus();
      if (s.status === "running") next.push({ key: "shazam", label: s.phase ?? "Identificazione mix", processed: s.processed, total: s.total });
    } catch { /* backend offline: ignora */ }
    if (alive.current) setJobs(next);
  }, []);

  const refresh = useCallback(() => { pollOnce(); }, [pollOnce]);

  useEffect(() => {
    alive.current = true;
    pollOnce();
    const id = setInterval(pollOnce, 2000);
    return () => { alive.current = false; clearInterval(id); };
  }, [pollOnce]);

  return (
    <JobsCtx.Provider value={{ refresh }}>
      {children}
      {jobs.length > 0 && <GlobalProgress jobs={jobs} />}
    </JobsCtx.Provider>
  );
}

function GlobalProgress({ jobs }: { jobs: Job[] }) {
  const j = jobs[0];
  const pct = j.total > 0 ? Math.round((j.processed / j.total) * 100) : null;
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface px-4 py-2.5">
      <div className="mx-auto flex max-w-5xl items-center gap-4">
        <span className="flex items-center gap-2 whitespace-nowrap text-[10px] font-medium uppercase tracking-wider text-muted">
          <Spinner className="h-3 w-3" /> {j.label}{jobs.length > 1 ? ` · +${jobs.length - 1}` : ""}
        </span>
        <div className="flex-1"><Progress value={pct} /></div>
        <span className="tnum whitespace-nowrap text-[10px] text-muted">{j.processed}/{j.total || "?"}{pct != null ? ` · ${pct}%` : ""}</span>
      </div>
    </div>
  );
}
