"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  scanJobStatus, startScan as apiStartScan, applyStatus, startApply as apiStartApply,
  type ScanJobState, type ApplyJobState,
} from "@/lib/api";
import { EqMeter } from "./ui";

const IDLE = {
  status: "idle" as const, phase: null, processed: 0, total: 0,
  result: null, error: null, started_at: null, finished_at: null,
};

type JobsApi = {
  scan: ScanJobState;
  apply: ApplyJobState;
  startScan: (rootIds?: number[]) => Promise<void>;
  startApply: () => Promise<void>;
  refresh: () => void;
};

const JobsCtx = createContext<JobsApi>({
  scan: IDLE, apply: IDLE,
  startScan: async () => {}, startApply: async () => {}, refresh: () => {},
});

export function useJobs() {
  return useContext(JobsCtx);
}

/**
 * Poller globale dei job (scan + apply). Vive nello shell: il progresso è
 * mostrato in una barra fissa in basso finché un job è in corso. Scan e apply
 * sono mutuamente esclusivi lato backend (409).
 */
export function JobsProvider({ children }: { children: ReactNode }) {
  const [scan, setScan] = useState<ScanJobState>(IDLE);
  const [apply, setApply] = useState<ApplyJobState>(IDLE);
  const alive = useRef(true);

  const pollOnce = useCallback(async () => {
    try {
      const s = await scanJobStatus();
      if (alive.current) setScan(s);
    } catch { /* backend offline */ }
    try {
      const a = await applyStatus();
      if (alive.current) setApply(a);
    } catch { /* backend offline */ }
  }, []);

  const refresh = useCallback(() => { pollOnce(); }, [pollOnce]);

  const startScan = useCallback(async (rootIds?: number[]) => {
    const s = await apiStartScan(rootIds);
    setScan(s);
  }, []);
  const startApply = useCallback(async () => {
    const a = await apiStartApply();
    setApply(a);
  }, []);

  useEffect(() => {
    alive.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    pollOnce();
    const id = setInterval(pollOnce, 1500);
    return () => { alive.current = false; clearInterval(id); };
  }, [pollOnce]);

  const api = useMemo<JobsApi>(
    () => ({ scan, apply, startScan, startApply, refresh }),
    [scan, apply, startScan, startApply, refresh],
  );

  const active = scan.status === "running"
    ? { label: "Scansione", job: scan as ScanJobState | ApplyJobState }
    : apply.status === "running"
    ? { label: "Applicazione", job: apply as ScanJobState | ApplyJobState }
    : null;

  return (
    <JobsCtx.Provider value={api}>
      {children}
      {active && <GlobalProgress label={active.label} job={active.job} />}
    </JobsCtx.Provider>
  );
}

function GlobalProgress({ label, job }: { label: string; job: ScanJobState | ApplyJobState }) {
  const pct = job.total > 0 ? Math.round((job.processed / job.total) * 100) : null;
  return (
    <div className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface px-4 py-2.5">
      <div className="mx-auto flex max-w-5xl items-center gap-4">
        <span className="whitespace-nowrap text-[10px] font-medium uppercase tracking-wider text-muted">
          {label}{job.phase ? ` · ${job.phase}` : ""}
        </span>
        <div className="flex-1"><EqMeter value={pct} className="h-6 w-full" /></div>
        <span className="tnum whitespace-nowrap text-[10px] text-muted">
          {job.processed}/{job.total || "?"}{pct != null ? ` · ${pct}%` : ""}
        </span>
      </div>
    </div>
  );
}
