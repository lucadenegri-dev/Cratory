import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/** Cella hero: numero grande tabellare con etichetta maiuscola.
 *  `big` è il taglio da frontespizio della dashboard. */
export function Figure({ label, value, big = false }: { label: string; value: ReactNode; big?: boolean }) {
  return (
    <div className={cn("border-b border-r border-border", big ? "px-5 py-6" : "px-4 py-3.5")}>
      <div className="text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div className={cn("tnum mt-1 font-semibold tracking-tight text-fg-strong", big ? "text-4xl sm:text-5xl" : "text-3xl")}>
        {value}
      </div>
    </div>
  );
}
