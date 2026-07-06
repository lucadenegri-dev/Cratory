"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { ChevronRight, ExternalLink, Upload } from "lucide-react";
import { cn } from "@/lib/cn";
import {
  fmtDate, startLibraryIndex, importRekordbox,
  type PipelineStatus, type RekordboxImportReport,
} from "@/lib/api";
import { Card, Alert, Spinner } from "@/components/ui";

/* Una fase della striscia: numero vivo + etichetta, "accesa" (pallino) se c'è
   lavoro pendente. Fasi con href navigano; Organizza e Analizza aprono un
   pannello inline; Indicizza lancia la scansione. */
type StageDef = {
  key: string;
  label: string;
  value: string;
  sub: string;
  hot: boolean;
  href?: string;
};

/** Pannello upload rekordbox.xml: riempie BPM/key mancanti e ricalcola l'energia,
 *  senza sovrascrivere valori già presenti (li imposta il backend). */
function RekordboxImportPanel({ pending, onImported }: { pending: number; onImported: () => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<RekordboxImportReport | null>(null);

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const r = await importRekordbox(file);
      setReport(r);
      onImported(); // aggiorna analyze_pending e copertura BPM/key/energia dopo l'import
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="flex flex-wrap items-start justify-between gap-3 border-t border-border px-4 py-3 text-xs text-muted">
      <div className="min-w-[16rem] flex-1">
        <p className="mb-2">
          Analizza le tracce in Rekordbox (beatgrid/tonalità), poi importa qui il file{" "}
          <code className="text-fg">rekordbox.xml</code> della collezione per completare BPM e tonalità
          (non sovrascrive valori già presenti).{" "}
          {pending > 0 ? `${pending} ${pending === 1 ? "traccia" : "tracce"} in attesa.` : "Nessuna traccia in attesa."}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".xml"
          disabled={busy}
          onChange={(e) => onFile(e.target.files?.[0])}
          className="block w-full max-w-sm text-xs text-muted file:mr-3 file:border file:border-border-strong file:bg-transparent file:px-3 file:py-1.5 file:text-xs file:font-medium file:uppercase file:tracking-wider file:text-fg hover:file:bg-elevated disabled:opacity-50"
        />
        {busy && <p className="mt-2 flex items-center gap-2"><Spinner /> Importazione in corso…</p>}
        {error && <div className="mt-2"><Alert tone="danger">⚠ {error}</Alert></div>}
        {report && (
          <div className="mt-2 grid max-w-sm grid-cols-2 gap-x-4 gap-y-1">
            <span>Nel file</span><span className="tnum text-fg">{report.in_file}</span>
            <span>Abbinate</span><span className="tnum text-fg">{report.matched}</span>
            <span>Non abbinate</span><span className="tnum text-fg">{report.unmatched}</span>
            <span>BPM impostati</span><span className="tnum text-fg">{report.bpm_set}</span>
            <span>Tonalità impostate</span><span className="tnum text-fg">{report.key_set}</span>
            <span>Energia ricalcolata</span><span className="tnum text-fg">{report.energy_set}</span>
          </div>
        )}
      </div>
      <Upload size={16} className="mt-0.5 shrink-0 text-faint" aria-hidden />
    </div>
  );
}

function StageCell({ s }: { s: StageDef }) {
  return (
    <div className="flex min-w-[8.5rem] flex-1 flex-col gap-0.5 px-4 py-3 text-left">
      <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted">
        {s.label}
        {s.hot && <span className="h-1.5 w-1.5 rounded-full bg-fg-strong" aria-hidden />}
      </span>
      <span className={cn("tnum text-lg font-semibold", s.hot ? "text-fg-strong" : "text-fg")}>{s.value}</span>
      <span className="whitespace-nowrap text-[10px] text-faint">{s.sub}</span>
    </div>
  );
}

export function PipelineStrip({ p, onRefresh }: { p: PipelineStatus; onRefresh: () => void }) {
  const [organizeOpen, setOrganizeOpen] = useState(false);
  const [analyzeOpen, setAnalyzeOpen] = useState(false);
  const [scanStarted, setScanStarted] = useState(false);

  const startScan = async () => {
    try {
      await startLibraryIndex();
      setScanStarted(true);
      onRefresh();
    } catch {
      /* 409 = LIBRARY_ROOT mancante o job già in corso: la striscia resta com'è */
    }
  };

  const diskConfigured = p.files_on_disk !== null;
  const stages: StageDef[] = [
    {
      key: "scopri", label: "Scopri", value: String(p.playlists),
      sub: "playlist importate", hot: p.total_tracks === 0, href: "/playlists",
    },
    {
      key: "acquisisci", label: "Acquisisci", value: String(p.wishlist),
      sub: p.download_active ? `download attivi · ${p.download_pending} in coda` : "in wishlist",
      hot: p.wishlist > 0 || p.download_active, href: "/downloads",
    },
    {
      key: "organizza", label: "Organizza ⤴",
      value: p.inbox_files === null ? "—" : String(p.inbox_files),
      sub: "enrich testuale + tag + organizza (in DjOrganizer)", hot: (p.inbox_files ?? 0) > 0,
    },
    {
      key: "indicizza", label: "Indicizza",
      value: scanStarted ? "…" : p.index_mismatch ? "≠" : "ok",
      sub: scanStarted
        ? "scansione avviata"
        : p.last_index_at
          ? `ultima: ${fmtDate(p.last_index_at)} · clic per scansionare`
          : "mai eseguita · clic per scansionare",
      hot: !scanStarted && diskConfigured && (p.index_mismatch === true || !p.last_index_at),
    },
    {
      key: "analizza", label: "Analizza ⤴", value: String(p.analyze_pending),
      sub: "analizza in Rekordbox → importa BPM/key", hot: p.analyze_pending > 0,
    },
    {
      key: "suona", label: "Suona", value: String(p.ready_for_set),
      sub: "pronte per un set", hot: false, href: "/set-builder",
    },
  ];

  const onStageClick = (key: string) => {
    if (key === "organizza") return setOrganizeOpen((v) => !v);
    if (key === "analizza") return setAnalyzeOpen((v) => !v);
    return startScan();
  };

  return (
    <Card>
      <div className="flex items-stretch overflow-x-auto">
        {stages.map((s, i) => (
          <div key={s.key} className="flex flex-1 items-center">
            {i > 0 && <ChevronRight size={14} className="shrink-0 text-faint" aria-hidden />}
            {s.href ? (
              <Link href={s.href} className="flex-1 transition-colors hover:bg-elevated">
                <StageCell s={s} />
              </Link>
            ) : (
              <button
                type="button"
                onClick={() => onStageClick(s.key)}
                className="flex-1 transition-colors hover:bg-elevated"
              >
                <StageCell s={s} />
              </button>
            )}
          </div>
        ))}
      </div>
      {organizeOpen && (
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border px-4 py-3 text-xs text-muted">
          <span>
            {p.inbox_files === null
              ? "Inbox non configurata: imposta SLSKD_DOWNLOAD_DIR nel .env del backend."
              : `${p.inbox_files} file audio in inbox aspettano il triage (DJPlayer), l'enrich testuale + tag e l'organizzazione (DjOrganizer); poi torna qui e indicizza.`}
          </span>
          {p.organizer_url && (
            <a
              href={p.organizer_url} target="_blank" rel="noreferrer"
              className="inline-flex shrink-0 items-center gap-1.5 text-fg-strong hover:underline"
            >
              Apri DjOrganizer <ExternalLink size={12} />
            </a>
          )}
        </div>
      )}
      {analyzeOpen && <RekordboxImportPanel pending={p.analyze_pending} onImported={onRefresh} />}
    </Card>
  );
}
