"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  analysisStatus, downloadStatus, generateStatus, libraryIndexStatus, shazamIdentifyStatus,
  streamingImportStatus,
  type AnalysisJobStatus, type DownloadStatus, type GenStatus, type LibraryIndexJob, type ShazamIdentifyState,
  type StreamingImportJobStatus,
} from "@/lib/api";
import {
  applyStatus, startApply as apiStartApply,
  providerRescanStatus, providerRescan as apiProviderRescan,
  integrityStatus, integrityCheck as apiIntegrityCheck,
  genreReviewStatus, genreReview as apiGenreReview,
  startScan as apiStartScan,
  type ApplyJobState, type GenreReviewBody, type GenreReviewJobState, type IntegrityJobState,
  type Location, type ProviderRescanBody, type ProviderRescanJobState, type ScanJobState,
} from "@/lib/organize/api";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";
import { EqMeter, Equalizer } from "./ui";

type Outcome = "done" | "error";

/** Stato neutro dei job Organize prima del primo poll. */
const IDLE = {
  status: "idle" as const, phase: null, processed: 0, total: 0,
  result: null, error: null, started_at: null, finished_at: null,
};

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
  /** Stato raw dell'analisi audio per la pagina /analysis. */
  analysis: AnalysisJobStatus | null;
  /** Stato raw dell'identificazione mix Shazam per la pagina /shazam. */
  shazamIdentify: ShazamIdentifyState | null;
  /** Stato raw della generazione set per /set-builder. */
  generation: GenStatus | null;
  /** Stato raw dell'import/sync streaming per le pagine playlist. */
  streamingImport: StreamingImportJobStatus | null;

  // --- Organize -------------------------------------------------------------
  /** Lo stesso job di `libraryIndex`, con il nome che usano le pagine Organize:
   *  da F4 scansione e indicizzazione sono un job solo, raggiungibile da due
   *  endpoint. Qui si polla una volta e si espone con entrambi i nomi. */
  scan: ScanJobState;
  apply: ApplyJobState;
  rescan: ProviderRescanJobState;
  integrity: IntegrityJobState;
  genreReviewJob: GenreReviewJobState;
  startScan: (locations?: Location[]) => Promise<void>;
  startApply: () => Promise<void>;
  startRescan: (body: ProviderRescanBody) => Promise<void>;
  startIntegrity: () => Promise<IntegrityJobState>;
  startGenreReview: (body?: GenreReviewBody) => Promise<void>;
};

const JobsCtx = createContext<JobsApi>({
  refresh: () => {}, startClientJob: () => {}, updateClientJob: () => {},
  endClientJob: () => {}, download: null, libraryIndex: null, analysis: null,
  shazamIdentify: null, generation: null, streamingImport: null,
  scan: IDLE, apply: IDLE, rescan: IDLE, integrity: { ...IDLE, available: true },
  genreReviewJob: IDLE,
  startScan: async () => {}, startApply: async () => {}, startRescan: async () => {},
  startIntegrity: async () => ({ ...IDLE, available: true }), startGenreReview: async () => {},
});

export function useJobs() {
  return useContext(JobsCtx);
}

const POLL_MS = 2000;
/** Quanto resta visibile l'esito di un job concluso con successo (gli errori
 * restano finché l'utente non li chiude). */
const OUTCOME_MS = 4000;
const MAX_ROWS = 3;

/**
 * Poller globale dei job in background. Vive nello shell, quindi continua a
 * girare anche cambiando pagina: il progresso è mostrato in una barra fissa in
 * basso finché un job è attivo. È l'unico poller: le pagine che mostrano il
 * dettaglio (downloads, settings) leggono gli stati raw da qui.
 *
 * - Job con status endpoint (download Soulseek, identificazione Shazam,
 *   indicizzazione libreria, generazione set): rilevati via polling.
 * - Job sincroni senza status endpoint (backfill etichette, DIG): registrati
 *   dalla pagina con startClientJob/updateClientJob/endClientJob.
 * - Alla transizione running -> done la riga resta OUTCOME_MS con l'esito,
 *   poi scompare; su error resta finché l'utente non la chiude con la ✕.
 * - Con la tab nascosta il polling di rete è in pausa (visibilitychange);
 *   al ritorno in foreground parte subito un poll e riprende l'intervallo.
 */
export function JobsProvider({ children }: { children: ReactNode }) {
  const t = useT();
  const [polled, setPolled] = useState<Job[]>([]);
  const [transient, setTransient] = useState<Job[]>([]);
  const [clientJobs, setClientJobs] = useState<Record<string, { label: string } & ClientJobPatch>>({});
  const [download, setDownload] = useState<DownloadStatus | null>(null);
  const [libraryIndex, setLibraryIndex] = useState<LibraryIndexJob | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisJobStatus | null>(null);
  const [shazamIdentify, setShazamIdentify] = useState<ShazamIdentifyState | null>(null);
  const [generation, setGeneration] = useState<GenStatus | null>(null);
  const [streamingImport, setStreamingImport] = useState<StreamingImportJobStatus | null>(null);
  const [apply, setApply] = useState<ApplyJobState>(IDLE);
  const [rescan, setRescan] = useState<ProviderRescanJobState>(IDLE);
  const [integrity, setIntegrity] = useState<IntegrityJobState>({ ...IDLE, available: true });
  const [genreReviewJob, setGenreReviewJob] = useState<GenreReviewJobState>(IDLE);
  const alive = useRef(true);
  const wasRunning = useRef<Set<string>>(new Set());
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  const pushOutcome = useCallback((job: Job) => {
    if (!alive.current) return;
    setTransient((t) => [...t.filter((x) => x.key !== job.key), job]);
    clearTimeout(timers.current[job.key]);
    delete timers.current[job.key];
    // Gli errori restano finché l'utente non li chiude: niente auto-remove.
    if (job.outcome === "error") return;
    timers.current[job.key] = setTimeout(() => {
      setTransient((t) => t.filter((x) => x.key !== job.key));
      delete timers.current[job.key];
    }, OUTCOME_MS);
  }, []);

  const dismissOutcome = useCallback((key: string) => {
    clearTimeout(timers.current[key]);
    delete timers.current[key];
    setTransient((t) => t.filter((x) => x.key !== key));
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

    const [s, d, li, an, gen, si, ap, re, ig, gr] = await Promise.allSettled([
      shazamIdentifyStatus(), downloadStatus(), libraryIndexStatus(), analysisStatus(), generateStatus(),
      streamingImportStatus(),
      applyStatus(), providerRescanStatus(), integrityStatus(), genreReviewStatus(),
    ]);

    if (s.status === "fulfilled") {
      const v = s.value;
      if (alive.current) setShazamIdentify(v);
      track(v.status, {
        key: "shazam", label: t.jobs.shazamIdentify, detail: v.phase ?? undefined,
        processed: v.processed, total: v.total, href: "/shazam",
      }, v.status === "error" ? (v.error ?? t.common.error) : t.jobs.completed);
    }
    if (d.status === "fulfilled") {
      const v = d.value;
      if (alive.current) setDownload(v);
      const pending = v.needs_review + v.not_found + v.failed;
      track(v.status, {
        key: "download", label: t.jobs.soulseekDownload, detail: v.current_label ?? undefined,
        processed: v.processed, total: v.total, href: "/wishlist",
      }, v.status === "error"
        ? (v.error ?? t.common.error)
        : t.jobs.downloadSummary(v.downloaded, pending));
    }
    if (li.status === "fulfilled") {
      const v = li.value;
      if (alive.current) setLibraryIndex(v);
      // `detail` porta la fase: da F4 il job attraversa scanning → linking →
      // inspecting → deduping, ed è la sola riga della barra che lo racconta.
      track(v.status, {
        key: "library-index", label: t.jobs.libraryIndex, detail: v.phase ?? undefined,
        processed: v.processed, total: v.total, href: "/settings",
      }, v.status === "error" ? (v.error ?? t.common.error) : t.jobs.completed);
    }
    if (an.status === "fulfilled") {
      const v = an.value;
      if (alive.current) setAnalysis(v);
      track(v.status, {
        key: "analysis", label: t.jobs.audioAnalysis, detail: v.current_label ?? undefined,
        processed: v.processed, total: v.total, href: "/analysis",
      }, v.status === "error" ? (v.error ?? t.common.error) : t.jobs.completed);
    }
    if (gen.status === "fulfilled") {
      const v = gen.value;
      if (alive.current) setGeneration(v);
      // Nessun processed/total lato backend (solo fase): riga sempre indeterminata.
      track(v.status, {
        key: "set-generation", label: t.jobs.setGeneration, detail: v.phase ?? undefined,
        processed: 0, total: 0, href: "/set-builder",
      }, v.status === "error" ? (v.error ?? t.common.error) : t.jobs.completed);
    }
    if (si.status === "fulfilled") {
      const v = si.value;
      if (alive.current) setStreamingImport(v);
      const phaseDetail = v.phase === "fetching" ? t.jobs.streamingImportPhaseFetching
        : v.phase === "importing" ? t.jobs.streamingImportPhaseImporting
        : undefined;
      track(v.status, {
        // Nel sync di massa `current_label` porta la playlist in corso col suo
        // progresso interno: più informativo della sola fase.
        key: "streaming-import", label: t.jobs.streamingImport, detail: v.current_label ?? phaseDetail,
        processed: v.processed, total: v.total, href: "/playlists",
      }, v.status === "error"
        ? (v.error ?? t.common.error)
        : v.sync_all ? t.jobs.syncAllSummary(v.sync_all.synced, v.sync_all.failed)
        : v.result ? t.jobs.streamingImportSummary(v.result.name, v.result.created)
        : t.jobs.completed);
    }
    // --- Organize. Niente riga per lo scan: è già `library-index` qui sopra,
    // stesso job visto dall'altro endpoint (vedi LibraryIndexJob in api/types).
    if (ap.status === "fulfilled") {
      const v = ap.value;
      if (alive.current) setApply(v);
      track(v.status, {
        key: "organize-apply", label: t.organize.jobs.apply, detail: v.phase ?? undefined,
        processed: v.processed, total: v.total, href: "/organize/plan",
      }, v.status === "error" ? (v.error ?? t.common.error) : t.jobs.completed);
    }
    if (re.status === "fulfilled") {
      const v = re.value;
      if (alive.current) setRescan(v);
      track(v.status, {
        key: "organize-rescan", label: t.organize.jobs.providerLookup, detail: v.phase ?? undefined,
        processed: v.processed, total: v.total, href: "/organize/issues",
      }, v.status === "error" ? (v.error ?? t.common.error) : t.jobs.completed);
    }
    if (ig.status === "fulfilled") {
      const v = ig.value;
      if (alive.current) setIntegrity(v);
      track(v.status, {
        key: "organize-integrity", label: t.organize.jobs.integrity, detail: v.phase ?? undefined,
        processed: v.processed, total: v.total, href: "/organize/files",
      }, v.status === "error" ? (v.error ?? t.common.error) : t.jobs.completed);
    }
    if (gr.status === "fulfilled") {
      const v = gr.value;
      if (alive.current) setGenreReviewJob(v);
      track(v.status, {
        key: "organize-genre-review", label: t.organize.jobs.genreReview, detail: v.phase ?? undefined,
        processed: v.processed, total: v.total, href: "/organize/issues",
      }, v.status === "error" ? (v.error ?? t.common.error) : t.jobs.completed);
    }

    wasRunning.current = nowRunning;
    if (alive.current) setPolled(next);
  }, [pushOutcome, t]);

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

  // --- Azioni Organize. Avviano e poi lasciano che sia il poller a raccontare
  // il resto: lo stato lo scrive pollOnce, non il valore di ritorno.
  const startScan = useCallback(async (locations?: Location[]) => {
    await apiStartScan(locations);
    refresh();
  }, [refresh]);
  const startApply = useCallback(async () => {
    await apiStartApply();
    refresh();
  }, [refresh]);
  const startRescan = useCallback(async (body: ProviderRescanBody) => {
    await apiProviderRescan(body);
    refresh();
  }, [refresh]);
  const startIntegrity = useCallback(async () => {
    const g = await apiIntegrityCheck(false);
    setIntegrity(g);
    return g;
  }, []);
  const startGenreReview = useCallback(async (body: GenreReviewBody = {}) => {
    await apiGenreReview(body);
    refresh();
  }, [refresh]);

  /* Riavvio automatico della scansione a fine Apply. È un COMPORTAMENTO, non
     un'API: nessun tipo lo protegge, e viveva nel provider di Organize che qui
     è stato assorbito. Esiste perché un apply sposta e ritagga file sul disco,
     quindi l'indice va riallineato. Si riconosce il fronte running→done e si
     riscansiona solo se qualche operazione è davvero atterrata. */
  const prevApplyStatus = useRef<ApplyJobState["status"]>(apply.status);
  useEffect(() => {
    const was = prevApplyStatus.current;
    prevApplyStatus.current = apply.status;
    if (was === "running" && apply.status === "done" && (apply.result?.applied_ops ?? 0) > 0) {
      startScan().catch(() => { /* backend offline o scan già in corso (409) */ });
    }
  }, [apply.status, apply.result, startScan]);

  useEffect(() => {
    alive.current = true;
    let id: ReturnType<typeof setInterval> | null = null;
    // Con la tab nascosta il polling di rete si ferma (i job client e i timer
    // degli esiti non vengono toccati); al ritorno visibile parte subito un
    // poll per riallineare la barra e l'intervallo riprende.
    const start = () => {
      if (id != null) return;
      pollOnce();
      id = setInterval(pollOnce, POLL_MS);
    };
    const stop = () => {
      if (id != null) {
        clearInterval(id);
        id = null;
      }
    };
    const onVisibility = () => {
      if (document.hidden) stop();
      else start();
    };
    document.addEventListener("visibilitychange", onVisibility);
    if (!document.hidden) start();
    const t = timers.current;
    return () => {
      alive.current = false;
      document.removeEventListener("visibilitychange", onVisibility);
      stop();
      Object.values(t).forEach(clearTimeout);
    };
  }, [pollOnce]);

  const api = useMemo<JobsApi>(
    () => ({
      refresh, startClientJob, updateClientJob, endClientJob,
      download, libraryIndex, analysis, shazamIdentify, generation, streamingImport,
      // `scan` è lo stesso job di `libraryIndex`: un poll, due nomi. IDLE finché
      // il primo poll non è tornato, così le pagine Organize non gestiscono null.
      scan: libraryIndex ?? IDLE,
      apply, rescan, integrity, genreReviewJob,
      startScan, startApply, startRescan, startIntegrity, startGenreReview,
    }),
    [refresh, startClientJob, updateClientJob, endClientJob, download, libraryIndex, analysis, shazamIdentify,
      generation, streamingImport, apply, rescan, integrity, genreReviewJob,
      startScan, startApply, startRescan, startIntegrity, startGenreReview],
  );

  // Dedup per chiave: un job che riparte entro OUTCOME_MS può comparire sia in
  // `polled` (in corso) sia in `transient` (esito residuo del run precedente).
  // Precedenza alla prima occorrenza → la riga attiva (polled) vince sull'esito,
  // e le chiavi React restano uniche.
  const seen = new Set<string>();
  const jobs: Job[] = [
    ...polled,
    ...Object.entries(clientJobs).map(([key, j]) => ({
      key, label: j.label, detail: j.detail,
      processed: j.processed ?? 0, total: j.total ?? 0,
      indeterminate: !j.total,
    })),
    ...transient,
  ].filter((j) => !seen.has(j.key) && seen.add(j.key));

  return (
    <JobsCtx.Provider value={api}>
      {children}
      {jobs.length > 0 && <GlobalProgress jobs={jobs} onDismiss={dismissOutcome} />}
    </JobsCtx.Provider>
  );
}

function GlobalProgress({ jobs, onDismiss }: { jobs: Job[]; onDismiss: (key: string) => void }) {
  const t = useT();
  const barRef = useRef<HTMLDivElement>(null);
  const [padH, setPadH] = useState(0);
  const visible = jobs.slice(0, MAX_ROWS);
  const extra = jobs.length - visible.length;

  // Annuncio screen-reader: solo gli esiti terminali (non le percentuali, che
  // spammerebbero). Cambia una volta quando un job finisce -> letto una volta.
  const announce = jobs
    .filter((j) => j.outcome)
    .map((j) => `${j.label}: ${j.outcome === "done" ? t.jobs.completed : t.common.error}`)
    .join(". ");

  // Spacer in flusso alto quanto la barra fissa: il fondo pagina resta leggibile.
  // Pubblica anche l'altezza in una CSS var globale, così elementi fixed esterni
  // (il player docked) possono posizionarsi SOPRA la barra invece di coprirla.
  useEffect(() => {
    const h = barRef.current?.offsetHeight ?? 0;
    setPadH(h);
    document.documentElement.style.setProperty("--jobs-bar-height", `${h}px`);
  }, [jobs]);

  // Quando la barra si smonta (nessun job attivo) azzera la var: il dock torna
  // al suo posto in basso.
  useEffect(
    () => () => {
      document.documentElement.style.setProperty("--jobs-bar-height", "0px");
    },
    [],
  );

  return (
    <>
      <div aria-hidden style={{ height: padH }} />
      <p className="sr-only" role="status" aria-live="polite">{announce}</p>
      <div
        ref={barRef}
        role="region"
        aria-label={t.jobs.regionLabel}
        className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface"
      >
        <div className="mx-auto max-w-5xl px-4">
          {visible.map((j, i) => <JobRow key={j.key} job={j} first={i === 0} onDismiss={onDismiss} />)}
          {extra > 0 && (
            <p className="border-t border-border py-1 text-center text-[10px] uppercase tracking-wider text-faint">
              {t.jobs.moreJobs(extra)}
            </p>
          )}
        </div>
      </div>
    </>
  );
}

function JobRow({ job, first, onDismiss }: { job: Job; first: boolean; onDismiss: (key: string) => void }) {
  const t = useT();
  const done = job.outcome === "done";
  const error = job.outcome === "error";
  const pct = done ? 100
    : job.indeterminate ? null
    : job.total > 0 ? Math.round((job.processed / job.total) * 100) : null;
  const body = (
    <div className={cn("flex items-center gap-4 py-2", !first && !error && "border-t border-border")}>
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
          <span aria-hidden className="flex justify-end text-faint"><Equalizer className="h-4 w-8" /></span>
        )}
      </span>
    </div>
  );
  const inner = job.href ? (
    <Link href={job.href} className="block outline-none hover:bg-elevated/40 focus-visible:bg-elevated/40">
      {body}
    </Link>
  ) : body;
  if (!error) return inner;
  // Riga errore: persiste finché non viene chiusa; la ✕ è fuori dal Link per
  // non annidare un bottone dentro un'ancora.
  return (
    <div className={cn("flex items-center", !first && "border-t border-border")}>
      <div className="min-w-0 flex-1">{inner}</div>
      <button
        type="button"
        aria-label={t.jobs.dismissError}
        title={t.jobs.dismissError}
        onClick={() => onDismiss(job.key)}
        className="ml-2 flex-none px-2 py-2 text-[13px] leading-none text-danger outline-none hover:text-fg-strong focus-visible:bg-elevated/40"
      >
        <span aria-hidden>✕</span>
      </button>
    </div>
  );
}
