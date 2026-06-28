"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { scanJobStatus, startScan as apiStartScan, type ScanJobState } from "@/lib/api";
import { EqMeter } from "./ui";

const IDLE: ScanJobState = {
  status: "idle", phase: null, processed: 0, total: 0,
  result: null, error: null, started_at: null, finished_at: null,
};

type JobsApi = {
  scan: ScanJobState;
  startScan: (rootIds?: number[]) => Promise<void>;
  refresh: () => void;
};

const JobsCtx = createContext<JobsApi>({ scan: IDLE, startScan: async () => {}, refresh: () => {} });

export function useJobs() {
  return useContext(JobsCtx);
}

/**
 * Poller globale del job di scan. Vive nello shell, quindi continua a girare
 * anche cambiando pagina: il progresso è mostrato in una barra fissa in basso
 * finché lo scan è in corso. Le pagine leggono `scan` dal context.
 */
export function JobsProvider({ children }: { children: ReactNode }) {
  const [scan, setScan] = useState<ScanJobState>(IDLE);
  const alive = useRef(true);

  const pollOnce = useCallback(async () => {
    try {
      const s = await scanJobStatus();
      if (alive.current) setScan(s);
    } catch {
      /* backend offline: mantieni l'ultimo stato noto */
    }
  }, []);

  const refresh = useCallback(() => { pollOnce(); }, [pollOnce]);

  const startScan = useCallback(async (rootIds?: number[]) => {
    const s = await apiStartScan(rootIds);
    setScan(s);
  }, []);

  useEffect(() => {
    alive.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    pollOnce();
    const id = setInterval(pollOnce, 1500);
    return () => { alive.current = false; clearInterval(id); };
  }, [pollOnce]);

  const api = useMemo<JobsApi>(() => ({ scan, startScan, refresh }), [scan, startScan, refresh]);

  return (
    <JobsCtx.Provider value={api}>
      {children}
      {scan.status === "running" && <GlobalProgress scan={scan} />}
    </JobsCtx.Provider>
  );
}

function GlobalProgress({ scan }: { scan: ScanJobState }) {
  const pct = scan.total > 0 ? Math.round((scan.processed / scan.total) * 100) : null;
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface px-4 py-2.5">
      <div className="mx-auto flex max-w-5xl items-center gap-4">
        <span className="whitespace-nowrap text-[10px] font-medium uppercase tracking-wider text-muted">
          Scansione{scan.phase ? ` · ${scan.phase}` : ""}
        </span>
        <div className="flex-1"><EqMeter value={pct} className="h-6 w-full" /></div>
        <span className="tnum whitespace-nowrap text-[10px] text-muted">
          {scan.processed}/{scan.total || "?"}{pct != null ? ` · ${pct}%` : ""}
        </span>
      </div>
    </div>
  );
}
