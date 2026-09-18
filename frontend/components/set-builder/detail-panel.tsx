"use client";

import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { type ManualAlternative, type ManualRow } from "@/lib/api";
import { Badge, Button, Textarea } from "@/components/ui";
import { TrackPlayButton } from "@/components/track-play-button";
import { useT } from "@/lib/i18n";

export type SaveState = "idle" | "saving" | "saved" | "error";

type Props = {
  row: ManualRow | null;
  saveState: SaveState;
  onSaveNote: (row: ManualRow, note: string) => void;
  onUseAlternative: (row: ManualRow, alt: ManualAlternative) => void;
  onRemoveAlternative: (row: ManualRow, alt: ManualAlternative) => void;
  onCompare: (row: ManualRow) => void;
};

/** Dettaglio della riga selezionata: dati tecnici con "sconosciuto" dove
 *  manca un valore, appunto salvato al blur solo se cambiato. */
export function DetailPanel({
  row, saveState, onSaveNote, onUseAlternative, onRemoveAlternative, onCompare,
}: Props) {
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

      <div className="border-t border-border pt-3">
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-xs uppercase tracking-wider text-muted">{t.sets.manual.alternativesTitle}</span>
          {row.alternatives.length > 0 && row.alternatives.length + (row.track ? 1 : 0) <= 4 && (
            <button type="button" onClick={() => onCompare(row)}
              className="text-xs text-muted underline-offset-4 hover:text-fg hover:underline">
              {t.sets.manual.compareButton(row.alternatives.length + (row.track ? 1 : 0))}
            </button>
          )}
        </div>
        {row.alternatives.length === 0 && <p className="text-sm text-muted">{t.sets.manual.alternativesEmpty}</p>}
        <ul className="divide-y divide-border">
          {row.track && row.alternatives.length > 0 && (
            <li className="flex items-center gap-2 py-1.5">
              <span className="min-w-0 flex-1 truncate text-sm">{row.track.artist} – {row.track.title}</span>
              <Badge>{t.sets.manual.activeBadge}</Badge>
            </li>
          )}
          {row.alternatives.map((a) => (
            <li key={a.id} className="flex items-center gap-2 py-1.5">
              <TrackPlayButton track={a.track} context={[a.track]} />
              <span className="min-w-0 flex-1 truncate text-sm">{a.track.artist} – {a.track.title}</span>
              <Button size="sm" variant="outline" onClick={() => onUseAlternative(row, a)}>
                {t.sets.manual.useAlternativeButton}
              </Button>
              <button type="button" title={t.sets.manual.removeAlternativeTitle}
                onClick={() => onRemoveAlternative(row, a)} className="text-muted hover:text-danger">
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
