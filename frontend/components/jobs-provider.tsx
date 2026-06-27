"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { enrichmentJobStatus, shazamIdentifyStatus } from "@/lib/api";
import { EqMeter } from "./ui";

type Job = { key: string; label: string; processed: number; total: number; indeterminate?: boolean };

type JobsApi = {
  /** Forza un poll immediato dei job lato backend (dopo aver avviato un job). */
  refresh: () => void;
  /** Registra un job sincrono lato client (es. backfill etichette) nella barra. */
  startClientJob: (key: string, label: string) => void;
  /** Rimuove un job client dalla barra. */
  endClientJob: (key: string) => void;
};

const JobsCtx = createContext<JobsApi>({ refresh: () => {}, startClientJob: () => {}, endClientJob: () => {} });

export function useJobs() {
  return useContext(JobsCtx);
}

/**
 * Poller globale dei job in background. Vive nello shell, quindi continua a
 * girare anche cambiando pagina: il progresso è mostrato in una barra fissa in
 * basso finché un job è attivo.
 *
 * - Job con status endpoint (arricchimento feature, identificazione Shazam):
 *   rilevati via polling.
 * - Job sincroni senza status endpoint (backfill etichette): registrati dalla
 *   pagina con startClientJob/endClientJob e mostrati come indeterminati.
 */
export function JobsProvider({ children }: { children: ReactNode }) {
  const [polled, setPolled] = useState<Job[]>([]);
  const [clientJobs, setClientJobs] = useState<Record<string, string>>({});
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
    if (alive.current) setPolled(next);
  }, []);

  const refresh = useCallback(() => { pollOnce(); }, [pollOnce]);

  const startClientJob = useCallback((key: string, label: string) => {
    setClientJobs((c) => ({ ...c, [key]: label }));
  }, []);
  const endClientJob = useCallback((key: string) => {
    setClientJobs((c) => {
      if (!(key in c)) return c;
      const n = { ...c }; delete n[key]; return n;
    });
  }, []);

  useEffect(() => {
    alive.current = true;
    pollOnce();
    const id = setInterval(pollOnce, 2000);
    return () => { alive.current = false; clearInterval(id); };
  }, [pollOnce]);

  const api = useMemo<JobsApi>(() => ({ refresh, startClientJob, endClientJob }), [refresh, startClientJob, endClientJob]);

  const jobs: Job[] = [
    ...polled,
    ...Object.entries(clientJobs).map(([key, label]) => ({ key, label, processed: 0, total: 0, indeterminate: true })),
  ];

  return (
    <JobsCtx.Provider value={api}>
      {children}
      {jobs.length > 0 && <GlobalProgress jobs={jobs} />}
    </JobsCtx.Provider>
  );
}

function GlobalProgress({ jobs }: { jobs: Job[] }) {
  const j = jobs[0];
  const pct = j.indeterminate ? null : (j.total > 0 ? Math.round((j.processed / j.total) * 100) : null);
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface px-4 py-2.5">
      <div className="mx-auto flex max-w-5xl items-center gap-4">
        <span className="whitespace-nowrap text-[10px] font-medium uppercase tracking-wider text-muted">
          {j.label}{jobs.length > 1 ? ` · +${jobs.length - 1}` : ""}
        </span>
        <div className="flex-1"><EqMeter value={pct} className="h-6 w-full" /></div>
        {!j.indeterminate && (
          <span className="tnum whitespace-nowrap text-[10px] text-muted">{j.processed}/{j.total || "?"}{pct != null ? ` · ${pct}%` : ""}</span>
        )}
      </div>
    </div>
  );
}
