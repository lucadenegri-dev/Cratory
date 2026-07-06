"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  downloadStatus, libraryIndexStatus, shazamIdentifyStatus,
  type DownloadStatus, type LibraryIndexJob,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { EqMeter } from "./ui";

type Outcome = "done" | "error";

type Job = {
  key: string;
  label: string;
  /** Riga secondaria: traccia in corso, fase, esito finale. */
  detail?: string;
  processed: number;
  total: number;
  indeterminate?: boolean;
  /** Click sulla riga -> pagina del job. */
  href?: string;
  /** Valorizzato sulle righe transienti di fine job. */
  outcome?: Outcome;
};

type ClientJobPatch = { processed?: number; total?: number; detail?: string };

type JobsApi = {
  /** Forza un poll immediato dei job lato backend (dopo aver avviato un job). */
  refresh: () => void;
  /** Registra un job sincrono lato client (es. backfill etichette) nella barra. */
  startClientJob: (key: string, label: string) => void;
  /** Aggiorna conteggi/dettaglio di un job client: la riga diventa determinata. */
  updateClientJob: (key: string, patch: ClientJobPatch) => void;
  /** Rimuove un job client dalla barra. */
  endClientJob: (key: string) => void;
  /** Stato raw dei download per la pagina /downloads (unico poller: questo). */
  download: DownloadStatus | null;
  /** Stato raw dell'indicizzazione libreria per la pagina settings. */
  libraryIndex: LibraryIndexJob | null;
};

const JobsCtx = createContext<JobsApi>({
  refresh: () => {}, startClientJob: () => {}, updateClientJob: () => {},
  endClientJob: () => {}, download: null, libraryIndex: null,
});

export function useJobs() {
  return useContext(JobsCtx);
}

const POLL_MS = 2000;
/** Quanto resta visibile l'esito di un job appena concluso. */
const OUTCOME_MS = 4000;
const MAX_ROWS = 3;

/**
 * Poller globale dei job in background. Vive nello shell, quindi continua a
 * girare anche cambiando pagina: il progresso è mostrato in una barra fissa in
 * basso finché un job è attivo. È l'unico poller: le pagine che mostrano il
 * dettaglio (downloads, settings) leggono gli stati raw da qui.
 *
 * - Job con status endpoint (download Soulseek, identificazione Shazam,
 *   indicizzazione libreria): rilevati via polling.
 * - Job sincroni senza status endpoint (backfill etichette, DIG): registrati
 *   dalla pagina con startClientJob/updateClientJob/endClientJob.
 * - Alla transizione running -> done/error la riga resta OUTCOME_MS con
 *   l'esito, poi scompare.
 */
export function JobsProvider({ children }: { children: ReactNode }) {
  const [polled, setPolled] = useState<Job[]>([]);
  const [transient, setTransient] = useState<Job[]>([]);
  const [clientJobs, setClientJobs] = useState<Record<string, { label: string } & ClientJobPatch>>({});
  const [download, setDownload] = useState<DownloadStatus | null>(null);
  const [libraryIndex, setLibraryIndex] = useState<LibraryIndexJob | null>(null);
  const alive = useRef(true);
  const wasRunning = useRef<Set<string>>(new Set());
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const pushOutcome = useCallback((job: Job) => {
    if (!alive.current) return;
    setTransient((t) => [...t.filter((x) => x.key !== job.key), job]);
    clearTimeout(timers.current[job.key]);
    timers.current[job.key] = setTimeout(() => {
      setTransient((t) => t.filter((x) => x.key !== job.key));
      delete timers.current[job.key];
    }, OUTCOME_MS);
  }, []);

  const pollOnce = useCallback(async () => {
    const next: Job[] = [];
    const nowRunning = new Set<string>();

    // Se "running" produce una riga; alla transizione running -> done/error
    // (vista al tick precedente) produce la riga esito transiente.
    const track = (status: string, job: Job, outcomeDetail: string) => {
      if (status === "running") {
        next.push(job);
        nowRunning.add(job.key);
      } else if (wasRunning.current.has(job.key) && (status === "done" || status === "error")) {
        pushOutcome({ ...job, outcome: status as Outcome, detail: outcomeDetail });
      }
    };

    const [s, d, li] = await Promise.allSettled([
      shazamIdentifyStatus(), downloadStatus(), libraryIndexStatus(),
    ]);

    if (s.status === "fulfilled") {
      const v = s.value;
      track(v.status, {
        key: "shazam", label: "Identificazione mix", detail: v.phase ?? undefined,
        processed: v.processed, total: v.total, href: "/shazam",
      }, v.status === "error" ? (v.error ?? "errore") : "completata");
    }
    if (d.status === "fulfilled") {
      const v = d.value;
      if (alive.current) setDownload(v);
      const pending = v.needs_review + v.not_found + v.failed;
      track(v.status, {
        key: "download", label: "Download Soulseek", detail: v.current_label ?? undefined,
        processed: v.processed, total: v.total, href: "/downloads",
      }, v.status === "error"
        ? (v.error ?? "errore")
        : `${v.downloaded} scaricate${pending > 0 ? ` · ${pending} da sistemare` : ""}`);
    }
    if (li.status === "fulfilled") {
      const v = li.value;
      if (alive.current) setLibraryIndex(v);
      track(v.status, {
        key: "library-index", label: "Indicizzazione libreria",
        processed: v.processed, total: v.total, href: "/settings",
      }, v.status === "error" ? (v.error ?? "errore") : "completata");
    }
    wasRunning.current = nowRunning;
    if (alive.current) setPolled(next);
  }, [pushOutcome]);

  const refresh = useCallback(() => { pollOnce(); }, [pollOnce]);

  const startClientJob = useCallback((key: string, label: string) => {
    setClientJobs((c) => ({ ...c, [key]: { label } }));
  }, []);
  const updateClientJob = useCallback((key: string, patch: ClientJobPatch) => {
    setClientJobs((c) => (key in c ? { ...c, [key]: { ...c[key], ...patch } } : c));
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
    const id = setInterval(pollOnce, POLL_MS);
    const t = timers.current;
    return () => {
      alive.current = false;
      clearInterval(id);
      Object.values(t).forEach(clearTimeout);
    };
  }, [pollOnce]);

  const api = useMemo<JobsApi>(
    () => ({ refresh, startClientJob, updateClientJob, endClientJob, download, libraryIndex }),
    [refresh, startClientJob, updateClientJob, endClientJob, download, libraryIndex],
  );

  const jobs: Job[] = [
    ...polled,
    ...Object.entries(clientJobs).map(([key, j]) => ({
      key, label: j.label, detail: j.detail,
      processed: j.processed ?? 0, total: j.total ?? 0,
      indeterminate: !j.total,
    })),
    ...transient,
  ];

  return (
    <JobsCtx.Provider value={api}>
      {children}
      {jobs.length > 0 && <GlobalProgress jobs={jobs} />}
    </JobsCtx.Provider>
  );
}

function GlobalProgress({ jobs }: { jobs: Job[] }) {
  const barRef = useRef<HTMLDivElement>(null);
  const [padH, setPadH] = useState(0);
  const visible = jobs.slice(0, MAX_ROWS);
  const extra = jobs.length - visible.length;

  // Spacer in flusso alto quanto la barra fissa: il fondo pagina resta leggibile.
  useEffect(() => {
    setPadH(barRef.current?.offsetHeight ?? 0);
  }, [jobs]);

  return (
    <>
      <div aria-hidden style={{ height: padH }} />
      <div ref={barRef} className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface">
        <div className="mx-auto max-w-5xl px-4">
          {visible.map((j, i) => <JobRow key={j.key} job={j} first={i === 0} />)}
          {extra > 0 && (
            <p className="border-t border-border py-1 text-center text-[10px] uppercase tracking-wider text-faint">
              +{extra} altri job
            </p>
          )}
        </div>
      </div>
    </>
  );
}

function JobRow({ job, first }: { job: Job; first: boolean }) {
  const done = job.outcome === "done";
  const error = job.outcome === "error";
  const pct = done ? 100
    : job.indeterminate ? null
    : job.total > 0 ? Math.round((job.processed / job.total) * 100) : null;
  const body = (
    <div className={cn("flex items-center gap-4 py-2", !first && "border-t border-border")}>
      <span className="w-36 flex-none sm:w-52">
        <span className="block truncate text-[10px] font-medium uppercase tracking-wider text-muted">
          {job.label}
        </span>
        {job.detail && (
          <span className={cn("block truncate text-[11px]", error ? "text-danger" : "text-faint")}>
            {job.detail}
          </span>
        )}
      </span>
      <div className="min-w-0 flex-1"><EqMeter value={pct} className="h-6 w-full" /></div>
      <span className="w-20 flex-none text-right">
        {pct != null ? (
          <>
            <span className="tnum block text-[15px] leading-tight text-fg-strong">{pct}%</span>
            {job.total > 0 && (
              <span className="tnum block text-[10px] text-muted">{job.processed}/{job.total}</span>
            )}
          </>
        ) : (
          <span className="block text-[15px] leading-tight text-faint">···</span>
        )}
      </span>
    </div>
  );
  if (!job.href) return body;
  return (
    <Link href={job.href} className="block outline-none hover:bg-elevated/40 focus-visible:bg-elevated/40">
      {body}
    </Link>
  );
}
