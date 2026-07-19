"use client";

import { Badge } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Sotto questa confidence il match Shazam e' dubbio (un solo campione concorde). */
export const DUBIOUS_CONFIDENCE_THRESHOLD = 60;

/** Badge "Dubbia" per le tracce identificate con un solo campione mai confermato.
 *  I set analizzati prima della confidence reale (80 fisso) non lo mostrano. */
export function ConfidenceBadge({ confidence }: { confidence: number | null }) {
  const t = useT();
  if (confidence == null || confidence >= DUBIOUS_CONFIDENCE_THRESHOLD) return null;
  return (
    <span title={t.shazam.detail.dubiousBadgeTitle} className="shrink-0">
      <Badge tone="warning">{t.shazam.detail.dubiousBadge}</Badge>
    </span>
  );
}
