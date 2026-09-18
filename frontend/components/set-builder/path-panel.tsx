"use client";

import { ArrowDown, ArrowUp, Bookmark, MoveHorizontal, Trash2 } from "lucide-react";
import { type ManualRow, type ManualSet } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

type Props = {
  set: ManualSet;
  selectedRowId: number | null;
  onSelect: (rowId: number) => void;
  onMove: (row: ManualRow, position: number) => void;
  onRemove: (row: ManualRow) => void;
  onGapAfter: (row: ManualRow) => void;
  onToReserve: (row: ManualRow) => void;
};

/** Le righe del percorso (tappa 1: un solo blocco main). Ogni riga e' un
 *  bottone che la seleziona; le azioni sono per id, mai per posizione. */
export function PathPanel({
  set, selectedRowId, onSelect, onMove, onRemove, onGapAfter, onToReserve,
}: Props) {
  const t = useT();
  const rows = set.blocks.filter((b) => b.placement === "main").flatMap((b) => b.rows);
  if (rows.length === 0) {
    return <p data-testid="path-panel" className="text-sm text-muted">{t.sets.manual.pathEmpty}</p>;
  }
  return (
    <ol data-testid="path-panel" className="divide-y divide-border">
      {rows.map((row, i) => (
        <li key={row.id} className={cn("flex items-center gap-2 py-1.5", selectedRowId === row.id && "bg-surface-2")}>
          <span className="tnum w-6 text-right text-xs text-muted">{row.position}</span>
          <button type="button" onClick={() => onSelect(row.id)} className="min-w-0 flex-1 text-left">
            {row.slot_kind === "gap" ? (
              <span className="inline-flex items-center gap-1 text-sm text-muted"><MoveHorizontal size={14} /> {t.sets.manual.gapLabel}</span>
            ) : (
              <span className="block truncate text-sm">{row.track?.artist} – {row.track?.title}</span>
            )}
          </button>
          {row.track && (
            <span className="tnum hidden text-xs text-muted sm:inline">
              {row.track.bpm ?? t.sets.manual.unknownValue} · {row.track.camelot_key ?? t.sets.manual.unknownValue}
            </span>
          )}
          <button type="button" title={t.sets.manual.moveUpTitle} disabled={i === 0} onClick={() => onMove(row, row.position - 1)} className="text-muted disabled:opacity-30"><ArrowUp size={14} /></button>
          <button type="button" title={t.sets.manual.moveDownTitle} disabled={i === rows.length - 1} onClick={() => onMove(row, row.position + 1)} className="text-muted disabled:opacity-30"><ArrowDown size={14} /></button>
          <button type="button" title={t.sets.manual.addGapTitle} onClick={() => onGapAfter(row)} className="text-muted"><MoveHorizontal size={14} /></button>
          {row.slot_kind === "track" && (
            <button type="button" title={t.sets.manual.toReserveTitle} onClick={() => onToReserve(row)} className="text-muted hover:text-fg"><Bookmark size={14} /></button>
          )}
          <button type="button" title={t.sets.manual.removeTitle} onClick={() => onRemove(row)} className="text-muted hover:text-danger"><Trash2 size={14} /></button>
        </li>
      ))}
    </ol>
  );
}
