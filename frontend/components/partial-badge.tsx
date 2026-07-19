"use client";

import { fmtDuration } from "@/lib/api";
import { Badge } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Un set e' "parziale" quando l'analisi si e' fermata prima della fine
 *  (recognizer giu'): identificato ma con `aborted_at_seconds` valorizzato. */
export function isPartial(set: { status: string; aborted_at_seconds: number | null }): boolean {
  return set.status === "done" && set.aborted_at_seconds != null;
}

/** Badge "PARZIALE" per un set la cui analisi si e' interrotta a meta'.
 *  Non rende nulla per i set completi. */
export function PartialBadge({ set }: { set: { status: string; aborted_at_seconds: number | null } }) {
  const t = useT();
  if (!isPartial(set)) return null;
  return (
    <span title={t.shazam.partialNote(fmtDuration(set.aborted_at_seconds!))} className="shrink-0">
      <Badge tone="warning">{t.shazam.partialBadge}</Badge>
    </span>
  );
}
