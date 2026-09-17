"use client";

import { useEffect, useState } from "react";
import { type ManualRow } from "@/lib/api";
import { Textarea } from "@/components/ui";
import { useT } from "@/lib/i18n";

export type SaveState = "idle" | "saving" | "saved" | "error";

type Props = {
  row: ManualRow | null;
  saveState: SaveState;
  onSaveNote: (row: ManualRow, note: string) => void;
};

/** Dettaglio della riga selezionata: dati tecnici con "sconosciuto" dove
 *  manca un valore, appunto salvato al blur solo se cambiato. */
export function DetailPanel({ row, saveState, onSaveNote }: Props) {
  const t = useT();
  const [draft, setDraft] = useState(row?.note ?? "");
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- riallineo il draft alla riga selezionata (stesso pattern di components/setup/path-field.tsx)
    setDraft(row?.note ?? "");
  }, [row?.id, row?.note]);
  if (!row) return <p className="text-sm text-muted">{t.sets.manual.detailEmpty}</p>;
  const tr = row.track;
  const stateLabel = { idle: "", saving: t.sets.manual.saving, saved: t.sets.manual.saved, error: t.sets.manual.saveError }[saveState];
  return (
    <div className="space-y-3" data-testid="detail-panel">
      <div className="font-medium">{tr ? `${tr.artist} – ${tr.title}` : t.sets.manual.gapLabel}</div>
      {tr && (
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <div><dt className="text-xs text-muted">BPM</dt><dd className="tnum">{tr.bpm ?? t.sets.manual.unknownValue}</dd></div>
          <div><dt className="text-xs text-muted">Camelot</dt><dd>{tr.camelot_key ?? t.sets.manual.unknownValue}</dd></div>
        </dl>
      )}
      <label className="block text-xs text-muted">{t.sets.manual.noteLabel}</label>
      <Textarea value={draft} placeholder={t.sets.manual.notePlaceholder} rows={4}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => { if (draft.trim() !== (row.note ?? "")) onSaveNote(row, draft); }} />
      <div className="text-xs text-muted" aria-live="polite">{stateLabel}</div>
    </div>
  );
}
