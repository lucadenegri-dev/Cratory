"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  scanJobStatus, startScan as apiStartScan, applyStatus, startApply as apiStartApply,
  providerRescanStatus, providerRescan as apiProviderRescan,
  type ScanJobState, type ApplyJobState, type ProviderRescanJobState, type ProviderRescanBody,
} from "@/lib/api";
import { EqMeter } from "./ui";
import { useT } from "@/lib/i18n";

const IDLE = {
  status: "idle" as const, phase: null, processed: 0, total: 0,
  result: null, error: null, started_at: null, finished_at: null,
};

type ProgressJob = { status: string; phase: string | null; processed: number; total: number };

type JobsApi = {
  scan: ScanJobState;
  apply: ApplyJobState;
  rescan: ProviderRescanJobState;
  startScan: (rootIds?: number[]) => Promise<void>;
  startApply: () => Promise<void>;
  startRescan: (body: ProviderRescanBody) => Promise<void>;
  refresh: () => void;
};

const JobsCtx = createContext<JobsApi>({
  scan: IDLE, apply: IDLE, rescan: IDLE,
  startScan: async () => {}, startApply: async () => {}, startRescan: async () => {}, refresh: () => {},
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
  const t = useT();
  const [scan, setScan] = useState<ScanJobState>(IDLE);
  const [apply, setApply] = useState<ApplyJobState>(IDLE);
  const [rescan, setRescan] = useState<ProviderRescanJobState>(IDLE);
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
    try {
      const r = await providerRescanStatus();
      if (alive.current) setRescan(r);
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
  const startRescan = useCallback(async (body: ProviderRescanBody) => {
    const r = await apiProviderRescan(body);
    setRescan(r);
  }, []);

  useEffect(() => {
    alive.current = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    pollOnce();
    const id = setInterval(pollOnce, 1500);
    return () => { alive.current = false; clearInterval(id); };
  }, [pollOnce]);

  const api = useMemo<JobsApi>(
    () => ({ scan, apply, rescan, startScan, startApply, startRescan, refresh }),
    [scan, apply, rescan, startScan, startApply, startRescan, refresh],
  );

  const active: { label: string; job: ProgressJob } | null = scan.status === "running"
    ? { label: t.jobs.scan, job: scan }
    : apply.status === "running"
    ? { label: t.jobs.apply, job: apply }
    : rescan.status === "running"
    ? { label: t.jobs.providerLookup, job: rescan }
    : null;

  return (
    <JobsCtx.Provider value={api}>
      {children}
      {active && <GlobalProgress label={active.label} job={active.job} />}
    </JobsCtx.Provider>
  );
}

function GlobalProgress({ label, job }: { label: string; job: ProgressJob }) {
  const pct = job.total > 0 ? Math.round((job.processed / job.total) * 100) : null;
  // Spaziatore in flusso alto quanto la barra fissa: così il fondo pagina non
  // resta tagliato/nascosto dietro la barra e lo scroll arriva fino in fondo.
  const barRef = useRef<HTMLDivElement>(null);
  const [padH, setPadH] = useState(0);
  useEffect(() => { setPadH(barRef.current?.offsetHeight ?? 0); }, []);
  return (
    <>
      <div aria-hidden style={{ height: padH }} />
      <div ref={barRef} className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface px-4 py-2.5">
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
    </>
  );
}
