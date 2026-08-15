import type { ReactNode } from "react";

/** Cella di misura: etichetta maiuscola e numero tabellare. Taglio e misure
 *  identici a `StageCell` della striscia pipeline, così i due pannelli della
 *  home si leggono come una cosa sola. */
export function Figure({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-r border-border px-4 py-3">
      <span className="text-[10px] uppercase tracking-wider text-muted">{label}</span>
      <span className="tnum text-lg font-semibold text-fg-strong">{value}</span>
    </div>
  );
}
