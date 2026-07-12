"use client";

import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { importRekordbox, type RekordboxImportReport } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Alert, Spinner } from "@/components/ui";

/** Card upload rekordbox.xml: riempie BPM/key mancanti e ricalcola l'energia.
 *  Di default non sovrascrive valori già presenti; il toggle "sovrascrivi" fa
 *  vincere la ri-analisi Rekordbox (il comportamento lo imposta il backend).
 *  Estratta da components/dashboard/pipeline.tsx (RekordboxImportPanel):
 *  stesso comportamento, stesse chiavi i18n t.dashboard.* (nessuna migrazione). */
export function RekordboxImportCard({ pending, onImported }: { pending: number; onImported: () => void }) {
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
