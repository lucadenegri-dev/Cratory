"use client";

import { X } from "lucide-react";
import { fmtDuration, type ManualAlternative, type ManualRow, type Track } from "@/lib/api";
import { Button } from "@/components/ui";
import { TrackPlayButton } from "@/components/track-play-button";
import { useT } from "@/lib/i18n";

type Candidate = { key: string; track: Track; alt: ManualAlternative | null };

type Props = {
  row: ManualRow;
  onUse: (alt: ManualAlternative) => void;
  onClose: () => void;
};

/** Confronto delle candidate di una riga: l'attiva e le sue alternative, coi
 *  dati tecnici affiancati e "sconosciuto" dove manca un valore. Il contesto
 *  di ascolto è esplicito: le tracce in confronto, nessun'altra. */
export function ComparePanel({ row, onUse, onClose }: Props) {
  const t = useT();
  const candidates: Candidate[] = [
    ...(row.track ? [{ key: "active", track: row.track, alt: null }] : []),
    ...row.alternatives.map((a) => ({ key: `alt-${a.id}`, track: a.track, alt: a })),
  ];
  const context = candidates.filter((c) => c.track.has_local_file).map((c) => c.track);
  return (
    <div data-testid="compare-panel" className="mt-3 border border-border p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-muted">{t.sets.manual.compareTitle}</span>
        <button type="button" onClick={onClose} title={t.sets.manual.compareCloseButton} className="text-muted hover:text-fg">
          <X size={14} />
        </button>
      </div>
      <p className="mb-2 text-xs text-muted">{t.sets.manual.compareHint}</p>
      <ul className="grid gap-2 sm:grid-cols-2">
        {candidates.map((c) => (
          <li key={c.key} className="border border-border p-2">
            <div className="mb-1 flex items-center gap-2">
              <TrackPlayButton track={c.track} context={context} />
              <span className="min-w-0 flex-1 truncate text-sm">{c.track.artist} – {c.track.title}</span>
            </div>
            <div className="flex flex-wrap gap-x-3 text-xs text-muted">
              <span className="tnum">{c.track.bpm ?? t.sets.manual.unknownValue}</span>
              <span>{c.track.camelot_key ?? t.sets.manual.unknownValue}</span>
              <span className="tnum">
                {c.track.duration_seconds ? fmtDuration(c.track.duration_seconds) : t.sets.manual.unknownValue}
              </span>
            </div>
            <div className="mt-2">
              {c.alt
                ? <Button size="sm" variant="outline" onClick={() => onUse(c.alt!)}>{t.sets.manual.useAlternativeButton}</Button>
                : <span className="text-xs text-muted">{t.sets.manual.activeBadge}</span>}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
