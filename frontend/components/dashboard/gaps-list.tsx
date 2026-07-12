import { AlertTriangle, Info } from "lucide-react";
import type { Gap } from "@/lib/api";

/** Elenco compatto dei gap strutturali della libreria (severità + descrizione). */
export function GapsList({ gaps, empty, max = 4 }: { gaps: Gap[]; empty: string; max?: number }) {
  if (gaps.length === 0) return <p className="text-xs text-faint">{empty}</p>;
  return (
    <div className="grid gap-1.5">
      {gaps.slice(0, max).map((g) => (
        <div key={g.gap_type} className="flex gap-1.5 text-xs" title={g.suggestion}>
          {g.severity === "warning"
            ? <AlertTriangle size={12} className="mt-0.5 shrink-0 text-muted" />
            : <Info size={12} className="mt-0.5 shrink-0 text-muted" />}
          <span className="min-w-0 text-fg">{g.description}</span>
        </div>
      ))}
    </div>
  );
}
