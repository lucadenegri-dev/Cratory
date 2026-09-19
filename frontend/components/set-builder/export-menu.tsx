"use client";

import { useState } from "react";
import { Download, FileText } from "lucide-react";
import { exportManualSet, errText, type ManualSet } from "@/lib/api";
import { Button, Modal } from "@/components/ui";
import { useT } from "@/lib/i18n";

type Formato = "text" | "csv" | "markdown" | "m3u8" | "prep" | "reserve";

const ESTENSIONI: Record<Formato, string> = {
  text: "txt", csv: "csv", markdown: "md", m3u8: "m3u8", prep: "md", reserve: "md",
};

type Props = { set: ManualSet };

/** Export del set preparato a mano. L'anteprima è LA RISPOSTA del server, non
 *  una seconda resa lato client: così non può divergere dal file scaricato. */
export function ExportMenu({ set }: Props) {
  const t = useT();
  const [aperto, setAperto] = useState(false);
  const [formato, setFormato] = useState<Formato | null>(null);
  const [testo, setTesto] = useState<string | null>(null);
  const [errore, setErrore] = useState<string | null>(null);

  const formati: [Formato, string][] = [
    ["text", t.sets.manual.exportFormatText],
    ["csv", t.sets.manual.exportFormatCsv],
    ["markdown", t.sets.manual.exportFormatMarkdown],
    ["m3u8", t.sets.manual.exportFormatM3u8],
    ["prep", t.sets.manual.exportFormatPrep],
    ["reserve", t.sets.manual.exportFormatReserve],
  ];

  const chiedi = async (f: Formato) => {
    setFormato(f);
    setTesto(null);
    setErrore(null);
    try { setTesto(await exportManualSet(set.id, f)); } catch (e) { setErrore(errText(e)); }
  };

  const scarica = () => {
    if (testo === null || formato === null) return;
    const blob = new Blob([testo], { type: "text/plain" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `${set.name}.${ESTENSIONI[formato]}`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div data-testid="export-menu" className="inline-flex flex-wrap items-center gap-2">
      <Button size="sm" variant="outline" onClick={() => setAperto(true)}>
        <FileText size={15} /> {t.sets.manual.exportButton}
      </Button>
      <Modal open={aperto} onClose={() => { setAperto(false); setFormato(null); setTesto(null); }}
        size="lg" title={t.sets.manual.exportButton}
        footer={
          <Button size="sm" variant="outline" disabled={testo === null} onClick={scarica}>
            <Download size={15} /> {t.sets.manual.exportDownloadButton}
          </Button>
        }>
        <div className="mb-3 flex flex-wrap gap-2">
          {formati.map(([f, etichetta]) => (
            <Button key={f} size="sm" variant={formato === f ? "primary" : "ghost"}
              onClick={() => void chiedi(f)}>{etichetta}</Button>
          ))}
        </div>
        {errore && <p className="text-sm text-danger">⚠ {errore}</p>}
        {testo !== null && (
          <>
            <div className="mb-1 text-xs uppercase tracking-wider text-muted">
              {t.sets.manual.exportPreviewTitle}
            </div>
            <pre data-testid="export-preview"
              className="max-h-80 overflow-auto whitespace-pre-wrap border border-border bg-surface-2 p-3 text-xs">
              {testo}
            </pre>
          </>
        )}
      </Modal>
    </div>
  );
}
