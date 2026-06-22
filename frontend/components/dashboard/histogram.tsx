import type { BpmBin } from "@/lib/api";

/** Istogramma monocromatico a barre verticali (altezza ∝ count/max). */
export function Histogram({ bins }: { bins: BpmBin[] }) {
  if (bins.length === 0) return <p className="text-sm text-faint">—</p>;
  const max = Math.max(...bins.map((b) => b.count), 1);
  const lo = bins[0].from;
  const hi = bins[bins.length - 1].to;
  return (
    <div>
      <div className="flex h-14 items-end gap-1">
        {bins.map((b, i) => (
          <div
            key={i}
            title={`${b.from.toFixed(0)}–${b.to.toFixed(0)} BPM · ${b.count}`}
            className="flex-1 bg-fg"
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
