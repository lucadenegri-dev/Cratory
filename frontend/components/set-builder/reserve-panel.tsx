"use client";

import { CornerUpLeft, Trash2 } from "lucide-react";
import { type ManualRow } from "@/lib/api";
import { TrackPlayButton } from "@/components/track-play-button";
import { useT } from "@/lib/i18n";

type Props = {
  rows: ManualRow[];
  onToPath: (row: ManualRow) => void;
  onRemove: (row: ManualRow) => void;
};

/** Le tracce tenute in tasca per la serata: non sono nel percorso e non
 *  contano nella durata del set. */
export function ReservePanel({ rows, onToPath, onRemove }: Props) {
  const t = useT();
  const playable = rows.map((r) => r.track).filter((tr): tr is NonNullable<typeof tr> => !!tr?.has_local_file);
  return (
    <div data-testid="reserve-panel" className="mt-4 border-t border-border pt-3">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-xs uppercase tracking-wider text-muted">{t.sets.manual.reserveTitle}</span>
        {rows.length > 0 && <span className="text-xs text-muted">{t.sets.manual.reserveMeta(rows.length)}</span>}
      </div>
      {rows.length === 0 && <p className="text-sm text-muted">{t.sets.manual.reserveEmpty}</p>}
      <ul className="divide-y divide-border">
        {rows.map((row) => (
          <li key={row.id} className="flex items-center gap-2 py-1.5">
            {row.track && <TrackPlayButton track={row.track} context={playable} />}
            <span className="min-w-0 flex-1 truncate text-sm">{row.track?.artist} – {row.track?.title}</span>
            <span className="tnum hidden text-xs text-muted sm:inline">
              {row.track?.bpm ?? t.sets.manual.unknownValue} · {row.track?.camelot_key ?? t.sets.manual.unknownValue}
            </span>
            <button type="button" title={t.sets.manual.toPathTitle} onClick={() => onToPath(row)} className="text-muted hover:text-fg">
              <CornerUpLeft size={14} />
            </button>
            <button type="button" title={t.sets.manual.removeTitle} onClick={() => onRemove(row)} className="text-muted hover:text-danger">
              <Trash2 size={14} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
