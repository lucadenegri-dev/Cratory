"use client";

import { useState } from "react";
import { cn } from "@/lib/cn";
import type { BpmBin } from "@/lib/api";

/** Istogramma monocromatico interattivo: passando il mouse evidenzia il bin e
 *  mostra range BPM + conteggio sopra le barre. */
export function Histogram({ bins }: { bins: BpmBin[] }) {
  const [hover, setHover] = useState<number | null>(null);
  if (bins.length === 0) return <p className="text-sm text-faint">—</p>;
  const max = Math.max(...bins.map((b) => b.count), 1);
  const lo = bins[0].from;
  const hi = bins[bins.length - 1].to;
  const active = hover != null ? bins[hover] : null;
  return (
    <div>
      <div className="mb-1 h-4 text-[10px] uppercase tracking-wider text-muted">
        {active && (
          <span className="tnum">{active.from.toFixed(0)}–{active.to.toFixed(0)} BPM · {active.count} {active.count === 1 ? "traccia" : "tracce"}</span>
        )}
      </div>
      <div className="flex h-14 items-end gap-1">
        {bins.map((b, i) => (
          <button
            key={i}
            type="button"
            aria-label={`${b.from.toFixed(0)}–${b.to.toFixed(0)} BPM: ${b.count}`}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
            onFocus={() => setHover(i)}
            onBlur={() => setHover(null)}
            className={cn(
              "flex-1 cursor-default transition-colors",
              hover === i ? "bg-fg-strong" : hover == null ? "bg-fg" : "bg-border-strong",
            )}
            style={{ height: `${Math.max(2, Math.round((b.count / max) * 100))}%` }}
          />
        ))}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-faint">
        <span className="tnum">{lo.toFixed(0)}</span>
        <span className="tnum">{hi.toFixed(0)}</span>
      </div>
    </div>
  );
}
