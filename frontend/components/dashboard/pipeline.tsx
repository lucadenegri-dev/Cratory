"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { ChevronRight, ExternalLink, Upload } from "lucide-react";
import { cn } from "@/lib/cn";
import {
  importRekordbox,
  type PipelineStatus, type RekordboxImportReport,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
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

/** Pannello upload rekordbox.xml: riempie BPM/key mancanti e ricalcola l'energia.
 *  Di default non sovrascrive valori già presenti; il toggle "sovrascrivi" fa
 *  vincere la ri-analisi Rekordbox (il comportamento lo imposta il backend). */
function RekordboxImportPanel({ pending, onImported }: { pending: number; onImported: () => void }) {
  const t = useT();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [overwrite, setOverwrite] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<RekordboxImportReport | null>(null);

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const r = await importRekordbox(file, overwrite);
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
          {t.dashboard.rekordboxIntroPrefix}<code className="text-fg">rekordbox.xml</code>{t.dashboard.rekordboxIntroSuffix}
          {t.dashboard.pendingTracks(pending)}
        </p>
        <input
          ref={inputRef}
          type="file"
          accept=".xml"
          disabled={busy}
          onChange={(e) => onFile(e.target.files?.[0])}
          className="block w-full max-w-sm text-xs text-muted file:mr-3 file:border file:border-border-strong file:bg-transparent file:px-3 file:py-1.5 file:text-xs file:font-medium file:uppercase file:tracking-wider file:text-fg hover:file:bg-elevated disabled:opacity-50"
        />
        <label className="mt-2 flex w-fit cursor-pointer items-center gap-2">
          <input
            type="checkbox"
            checked={overwrite}
            disabled={busy}
            onChange={(e) => setOverwrite(e.target.checked)}
            className="accent-fg-strong"
          />
          <span>
            {t.dashboard.overwriteLabel}
          </span>
        </label>
        {busy && <p className="mt-2 flex items-center gap-2"><Spinner /> {t.dashboard.importing}</p>}
        {error && <div className="mt-2"><Alert tone="danger">⚠ {error}</Alert></div>}
        {report && (
          <div className="mt-2 grid max-w-sm grid-cols-2 gap-x-4 gap-y-1">
            <span>{t.dashboard.reportInFile}</span><span className="tnum text-fg">{report.in_file}</span>
            <span>{t.dashboard.reportMatched}</span><span className="tnum text-fg">{report.matched}</span>
            <span>{t.dashboard.reportUnmatched}</span><span className="tnum text-fg">{report.unmatched}</span>
            <span>{t.dashboard.reportBpmSet}</span><span className="tnum text-fg">{report.bpm_set}</span>
            <span>{t.dashboard.reportKeySet}</span><span className="tnum text-fg">{report.key_set}</span>
            <span>{t.dashboard.reportEnergySet}</span><span className="tnum text-fg">{report.energy_set}</span>
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
      <span className="text-[10px] leading-tight text-faint">{s.sub}</span>
    </div>
  );
}

export function PipelineStrip({ p, onRefresh }: { p: PipelineStatus; onRefresh: () => void }) {
  const t = useT();
  const [organizeOpen, setOrganizeOpen] = useState(false);
  const [analyzeOpen, setAnalyzeOpen] = useState(false);

  const stages: StageDef[] = [
    {
      key: "scopri", label: t.dashboard.stageDiscover, value: String(p.playlists),
      sub: t.dashboard.stageDiscoverSub, hot: p.total_tracks === 0, href: "/playlists",
    },
    {
      key: "acquisisci", label: t.dashboard.stageAcquire, value: String(p.wishlist),
      sub: t.dashboard.stageAcquireSub(p.download_active, p.download_pending),
      hot: p.wishlist > 0 || p.download_active, href: "/downloads",
    },
    {
      key: "organizza", label: t.dashboard.stageOrganize,
      value: p.inbox_files === null ? "—" : String(p.inbox_files),
      sub: t.dashboard.stageOrganizeSub, hot: (p.inbox_files ?? 0) > 0,
    },
    {
      key: "analizza", label: t.dashboard.stageAnalyze, value: String(p.analyze_pending),
      sub: t.dashboard.stageAnalyzeSub, hot: p.analyze_pending > 0,
    },
    {
      key: "suona", label: t.dashboard.stagePlay, value: String(p.ready_for_set),
      sub: t.dashboard.stagePlaySub, hot: false, href: "/set-builder",
    },
  ];

  const onStageClick = (key: string) => {
    if (key === "organizza") return setOrganizeOpen((v) => !v);
    return setAnalyzeOpen((v) => !v);
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
              ? t.dashboard.inboxNotConfigured
              : t.dashboard.inboxWaiting(p.inbox_files)}
          </span>
          {p.organizer_url && (
            <a
              href={p.organizer_url} target="_blank" rel="noreferrer"
              className="inline-flex shrink-0 items-center gap-1.5 text-fg-strong hover:underline"
            >
              {t.dashboard.openSortory} <ExternalLink size={12} />
            </a>
          )}
        </div>
      )}
      {analyzeOpen && <RekordboxImportPanel pending={p.analyze_pending} onImported={onRefresh} />}
    </Card>
  );
}
