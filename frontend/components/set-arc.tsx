import type { SetlistTrack } from "@/lib/api";

/* Arco del set: sparkline doppia (BPM linea piena + Energia area) sopra la scaletta.
   Monocromo, filetti a 1px, cifre tabulari — coerente col linguaggio "indice tipografico".
   Nessuna animazione: statico, quindi neutro rispetto a prefers-reduced-motion. */

const W = 600;         // viewBox width (scala con il container via preserveAspectRatio)
const H = 72;          // viewBox height
const PT = 10;         // padding top
const PB = 14;         // padding bottom (spazio numeri energia)
const PX = 4;          // padding orizzontale

type Pt = { x: number; bpm: number | null; energy: number | null; pos: number };

function scale(v: number, min: number, max: number) {
  if (max <= min) return H - PB; // serie piatta → linea bassa
  const t = (v - min) / (max - min);
  return H - PB - t * (H - PT - PB);
}

function polyline(pts: { x: number; y: number }[]) {
  return pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ");
}

export function SetArc({ tracks }: { tracks: SetlistTrack[] }) {
  const data: Pt[] = tracks.map((st, i) => ({
    x: PX + (tracks.length <= 1 ? W / 2 - PX : (i * (W - 2 * PX)) / (tracks.length - 1)),
    bpm: st.track.bpm ?? null,
    energy: st.track.energy ?? null,
    pos: st.position,
  }));

  const bpms = data.map((d) => d.bpm).filter((v): v is number => v != null);
  const hasBpm = bpms.length >= 2;
  const hasEnergy = data.filter((d) => d.energy != null).length >= 2;

  if (!hasBpm && !hasEnergy) {
    return (
      <div className="border border-border bg-bg px-3 py-2.5 text-xs text-muted">
        <span className="font-semibold uppercase tracking-wide">Arco del set</span>
        <span className="ml-2 text-faint">dati BPM/energia insufficienti per tracciare l&apos;arco</span>
      </div>
    );
  }

  const bpmMin = hasBpm ? Math.min(...bpms) : 0;
  const bpmMax = hasBpm ? Math.max(...bpms) : 0;

  const bpmPts = data.filter((d) => d.bpm != null).map((d) => ({ x: d.x, y: scale(d.bpm as number, bpmMin, bpmMax) }));
  const enPts = data.filter((d) => d.energy != null).map((d) => ({ x: d.x, y: scale(d.energy as number, 0, 100) }));
  const enArea = enPts.length
    ? `${enPts[0].x.toFixed(1)},${(H - PB).toFixed(1)} ${polyline(enPts)} ${enPts[enPts.length - 1].x.toFixed(1)},${(H - PB).toFixed(1)}`
    : "";

  const label = [
    hasBpm && `BPM da ${bpmMin.toFixed(0)} a ${bpmMax.toFixed(0)}`,
    hasEnergy && `energia da ${data.find((d) => d.energy != null)?.energy} a ${[...data].reverse().find((d) => d.energy != null)?.energy}`,
    `${tracks.length} tracce`,
  ].filter(Boolean).join(", ");

  return (
    <div className="border border-border bg-bg p-3">
      <div className="mb-1.5 flex items-center justify-between gap-3">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted">Arco del set</span>
        <span className="flex items-center gap-3 text-[10px] uppercase tracking-wider text-muted">
          <span className="flex items-center gap-1"><span className="inline-block h-px w-3 bg-fg-strong" /> BPM</span>
          <span className="flex items-center gap-1"><span className="inline-block h-1.5 w-3 bg-elevated" /> Energia</span>
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="h-16 w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label={`Arco del set: ${label}`}
      >
        {/* gridlines */}
        {[PT, (PT + (H - PB)) / 2, H - PB].map((y, i) => (
          <line key={i} x1={PX} y1={y} x2={W - PX} y2={y} stroke="var(--color-border)" strokeWidth={1} vectorEffect="non-scaling-stroke" />
        ))}
        {/* energia: area riempita sotto la linea BPM */}
        {hasEnergy && <polygon points={enArea} fill="var(--color-elevated)" />}
        {/* BPM: linea + nodi quadrati */}
        {hasBpm && (
          <>
            <polyline points={polyline(bpmPts)} fill="none" stroke="var(--color-fg-strong)" strokeWidth={1.5} vectorEffect="non-scaling-stroke" strokeLinejoin="round" />
            {bpmPts.map((p, i) => (
              <rect key={i} x={p.x - 1.5} y={p.y - 1.5} width={3} height={3} fill="var(--color-fg-strong)" vectorEffect="non-scaling-stroke" />
            ))}
          </>
        )}
      </svg>
      {hasBpm && (
        <div className="mt-1 flex justify-between text-[10px] text-faint tnum">
          <span>{bpmMin.toFixed(0)} BPM</span>
          <span>{bpmMax.toFixed(0)} BPM</span>
        </div>
      )}
    </div>
  );
}
