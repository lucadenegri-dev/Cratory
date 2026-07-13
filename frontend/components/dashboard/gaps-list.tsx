import { AlertTriangle, Info } from "lucide-react";
import type { Gap } from "@/lib/api";
import { translateGap } from "@/lib/i18n";

/** Elenco compatto dei gap strutturali della libreria (severità + descrizione). */
export function GapsList({ gaps, empty, max = 4 }: { gaps: Gap[]; empty: string; max?: number }) {
  if (gaps.length === 0) return <p className="text-xs text-faint">{empty}</p>;
  return (
    <div className="grid gap-1.5">
      {gaps.slice(0, max).map((g) => {
        const { description, suggestion } = translateGap(g.gap_type, g.params, g);
        return (
          <div key={g.gap_type} className="flex gap-1.5 text-xs" title={suggestion}>
            {g.severity === "warning"
              ? <AlertTriangle size={12} className="mt-0.5 shrink-0 text-muted" />
              : <Info size={12} className="mt-0.5 shrink-0 text-muted" />}
            <span className="min-w-0 text-fg">{description}</span>
          </div>
        );
      })}
    </div>
  );
}
