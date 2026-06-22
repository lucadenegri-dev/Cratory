import type { ReactNode } from "react";

/** Cella hero: numero grande tabellare con etichetta maiuscola. */
export function Figure({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="border-b border-r border-border px-4 py-3.5">
      <div className="text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div className="tnum mt-1 text-3xl font-semibold tracking-tight text-fg-strong">{value}</div>
    </div>
  );
}
