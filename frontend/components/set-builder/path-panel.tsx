"use client";

import { useState, type ReactNode } from "react";
import {
  ArrowDown, ArrowUp, Bookmark, Inbox, MoveHorizontal, Pencil, Scissors, Sparkles, Trash2,
} from "lucide-react";
import { type ManualBlock, type ManualRow, type ManualSet } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

type Props = {
  set: ManualSet;
  selectedRowId: number | null;
  checkedRowIds: number[];
  onSelect: (rowId: number) => void;
  onCheck: (rowId: number) => void;
  onMove: (row: ManualRow, position: number) => void;
  onRemove: (row: ManualRow) => void;
  onGapAfter: (row: ManualRow) => void;
  onToReserve: (row: ManualRow) => void;
  onRenameBlock: (block: ManualBlock, name: string) => void;
  onMoveBlock: (block: ManualBlock, position: number) => void;
  onToBench: (block: ManualBlock) => void;
  onSplitBlock: (block: ManualBlock) => void;
  fillingRowId: number | null;
  onStartFill: (row: ManualRow | null) => void;
  renderFill: (row: ManualRow) => ReactNode;
};

/** Il percorso, diviso in sequenze (i blocchi `main`). Le azioni sono per id,
 *  mai per posizione; le frecce di riga muovono DENTRO la sequenza, quindi ai
 *  suoi estremi sono spente: per attraversare un confine si sposta la sequenza. */
export function PathPanel({
  set, selectedRowId, checkedRowIds, onSelect, onCheck, onMove, onRemove, onGapAfter,
  onToReserve, onRenameBlock, onMoveBlock, onToBench, onSplitBlock,
  fillingRowId, onStartFill, renderFill,
}: Props) {
  const t = useT();
  const [renaming, setRenaming] = useState<number | null>(null);
  const blocks = set.blocks.filter((b) => b.placement === "main");
  if (blocks.every((b) => b.rows.length === 0)) {
    return <p data-testid="path-panel" className="text-sm text-muted">{t.sets.manual.pathEmpty}</p>;
  }
  return (
    <div data-testid="path-panel">
      {blocks.map((block, bi) => (
        <section key={block.id} className={cn(bi > 0 && "mt-3 border-t border-border pt-2")}>
          <div className="mb-1 flex items-center gap-2">
            {renaming === block.id ? (
              <input autoFocus defaultValue={block.name ?? ""}
                placeholder={t.sets.manual.sequenceNamePlaceholder}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    onRenameBlock(block, (e.target as HTMLInputElement).value);
                    setRenaming(null);
                  }
                  if (e.key === "Escape") setRenaming(null);
                }}
                onBlur={() => setRenaming(null)}
                className="min-w-0 flex-1 rounded border border-border bg-surface px-2 py-0.5 text-sm" />
            ) : (
              <span className="min-w-0 flex-1 truncate text-xs uppercase tracking-wider text-muted">
                {block.name ?? t.sets.manual.sequenceUnnamed}
              </span>
            )}
            <span className="text-xs text-muted">{t.sets.manual.sequenceMeta(block.rows.length)}</span>
            <button type="button" title={t.sets.manual.renameSequenceTitle}
              onClick={() => setRenaming(block.id)} className="text-muted hover:text-fg"><Pencil size={13} /></button>
            <button type="button" title={t.sets.manual.moveSequenceUpTitle} disabled={bi === 0}
              onClick={() => onMoveBlock(block, bi)} className="text-muted disabled:opacity-30"><ArrowUp size={13} /></button>
            <button type="button" title={t.sets.manual.moveSequenceDownTitle} disabled={bi === blocks.length - 1}
              onClick={() => onMoveBlock(block, bi + 2)} className="text-muted disabled:opacity-30"><ArrowDown size={13} /></button>
            <button type="button" title={t.sets.manual.toBenchTitle}
              onClick={() => onToBench(block)} className="text-muted hover:text-fg"><Inbox size={13} /></button>
            <button type="button" title={t.sets.manual.splitSequenceTitle} disabled={blocks.length === 1}
              onClick={() => onSplitBlock(block)} className="text-muted hover:text-fg disabled:opacity-30"><Scissors size={13} /></button>
          </div>
          <ol className="divide-y divide-border">
            {block.rows.map((row, i) => (
              <li key={row.id} data-row={row.id}
                className={cn("flex items-center gap-2 py-1.5", selectedRowId === row.id && "bg-surface-2")}>
                <input type="checkbox" aria-label={t.sets.manual.selectRowLabel}
                  checked={checkedRowIds.includes(row.id)} onChange={() => onCheck(row.id)} />
                <span className="tnum w-6 text-right text-xs text-muted">{row.position}</span>
                <button type="button" onClick={() => onSelect(row.id)} className="min-w-0 flex-1 text-left">
                  {row.slot_kind === "gap" ? (
                    <span className="inline-flex items-center gap-1 text-sm text-muted"><MoveHorizontal size={14} /> {t.sets.manual.gapLabel}</span>
                  ) : (
                    <span className="block truncate text-sm">{row.track?.artist} – {row.track?.title}</span>
                  )}
                </button>
                {row.track && (
                  // Colonna stretta: il titolo ha la precedenza sui dati tecnici,
                  // che senza un limite lo schiacciavano a una lettera.
                  <span className="tnum hidden max-w-32 truncate text-xs text-muted xl:inline">
                    {row.track.bpm ?? t.sets.manual.unknownValue}{" "}
                    · {row.track.camelot_key ?? t.sets.manual.unknownValue}
                  </span>
                )}
                <button type="button" title={t.sets.manual.moveUpTitle} disabled={i === 0} onClick={() => onMove(row, row.position - 1)} className="text-muted disabled:opacity-30"><ArrowUp size={14} /></button>
                <button type="button" title={t.sets.manual.moveDownTitle} disabled={i === block.rows.length - 1} onClick={() => onMove(row, row.position + 1)} className="text-muted disabled:opacity-30"><ArrowDown size={14} /></button>
                {row.slot_kind === "gap" && (
                  <button type="button" title={t.sets.manual.fillGapTitle}
                    onClick={() => onStartFill(row)} className="text-muted hover:text-fg"><Sparkles size={14} /></button>
                )}
                <button type="button" title={t.sets.manual.addGapTitle} onClick={() => onGapAfter(row)} className="text-muted"><MoveHorizontal size={14} /></button>
                {row.slot_kind === "track" && (
                  <button type="button" title={t.sets.manual.toReserveTitle} onClick={() => onToReserve(row)} className="text-muted hover:text-fg"><Bookmark size={14} /></button>
                )}
                <button type="button" title={t.sets.manual.removeTitle} onClick={() => onRemove(row)} className="text-muted hover:text-danger"><Trash2 size={14} /></button>
              </li>
            ))}
            {block.rows.filter((r) => r.id === fillingRowId).map((row) => (
              <li key={`fill-${row.id}`}>{renderFill(row)}</li>
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}
