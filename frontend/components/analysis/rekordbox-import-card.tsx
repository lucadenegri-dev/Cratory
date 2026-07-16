"use client";

import { useRef, useState } from "react";
import { importRekordbox, type RekordboxImportReport } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Alert, Badge, Checkbox, Field, Spinner } from "@/components/ui";

/** Sezione "import rekordbox.xml": riempie BPM/key mancanti e ricalcola l'energia.
 *  È la sorgente PRIMARIA (regola 2 di CLAUDE.md), quindi vive in cima alla card
 *  Sorgenti, non come card di pari rango accanto all'analisi in-app.
 *  Di default non sovrascrive i valori manuali; sui valori 'cratory' vince sempre
 *  (backend: rekordbox_import.py:132), quindi l'analisi in-app non blocca Rekordbox.
 *  Il toggle "sovrascrivi" estende la vittoria anche a manuali e rekordbox. */
export function RekordboxImportCard({ onImported }: { onImported: () => void }) {
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
      onImported(); // aggiorna copertura e conteggi dopo l'import
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const reportRows: [string, number][] = report ? [
    [t.analysis.reportInFile, report.in_file],
    [t.analysis.reportMatched, report.matched],
    [t.analysis.reportUnmatched, report.unmatched],
    [t.analysis.reportBpmSet, report.bpm_set],
    [t.analysis.reportKeySet, report.key_set],
    [t.analysis.reportEnergySet, report.energy_set],
  ] : [];

  return (
    <section className="px-5 py-4">
      <div className="mb-2 flex items-center gap-2">
        <h4 className="text-sm font-semibold uppercase tracking-wider text-fg-strong">
          {t.analysis.rekordboxHeading}
        </h4>
        <Badge tone="primary">{t.analysis.rekordboxPrimaryTag}</Badge>
      </div>

      {/* Niente conteggio "in attesa" qui: rekordbox_pending è calcolato come
          `bpm is None or not camelot_key`, cioè esattamente le tracce non pronte
          già annunciate dal lede. Stesso numero, stesse tracce, due nomi. */}
      <p className="mb-3 max-w-[60ch] text-sm text-muted">
        {t.analysis.rekordboxIntroPrefix}<code className="text-fg">rekordbox.xml</code>{t.analysis.rekordboxIntroSuffix}
      </p>

      <div className="max-w-sm">
        {/* Field avvolge in <label>: dà il nome accessibile che l'input file non aveva. */}
        <Field label={t.analysis.fileInputLabel}>
          <input
            ref={inputRef}
            type="file"
            accept=".xml"
            disabled={busy}
            onChange={(e) => onFile(e.target.files?.[0])}
            className="block w-full text-xs text-muted file:mr-3 file:border file:border-border-strong file:bg-transparent file:px-3 file:py-1.5 file:text-xs file:font-medium file:uppercase file:tracking-wider file:text-fg hover:file:bg-elevated disabled:opacity-50"
          />
        </Field>
      </div>

      <div className="mt-3">
        <Checkbox
          label={<span className="text-xs">{t.analysis.overwriteLabel}</span>}
          checked={overwrite}
          disabled={busy}
          onChange={setOverwrite}
        />
      </div>

      {busy && (
        <p className="mt-3 flex items-center gap-2 text-xs text-muted" role="status">
          <Spinner /> {t.analysis.importing}
        </p>
      )}
      {error && <div className="mt-3"><Alert tone="danger">⚠ {error}</Alert></div>}
      {report && (
        <dl className="mt-3 grid max-w-sm grid-cols-2 gap-x-4 gap-y-1 text-xs">
          {reportRows.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted">{label}</dt>
              <dd className="tnum text-fg">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
