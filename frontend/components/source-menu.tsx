"use client";

import { useEffect, useRef, useState } from "react";
import { fmtDate, type ScanRoot } from "@/lib/api";
import { AddSource } from "./add-source";
import { useJobs } from "./jobs-provider";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

// Tendina sorgenti: filtra i file (selezione riga) e gestisce le radici
// (scan/elimina per riga + aggiungi). Sostituisce la vecchia pagina Sources.
export function SourceMenu({
  roots, selectedId, onSelect, onScanRoot, onDelete, onAdded, deletingId,
}: {
  roots: ScanRoot[];
  selectedId: number | null;
  onSelect: (id: number | null) => void;
  onScanRoot: (id: number) => void;
  onDelete: (id: number) => void;
  onAdded: () => void;
  deletingId: number | null;
}) {
  const t = useT();
  const { scan } = useJobs();
  const running = scan.status === "running";
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // chiudi cliccando fuori dalla tendina
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const selected = roots.find((r) => r.id === selectedId) ?? null;
  const triggerLabel = selected
    ? (selected.label || selected.path)
    : t.files.allSourcesN(roots.length);

  const select = (id: number | null) => { onSelect(id); setOpen(false); };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-2 border border-border bg-bg px-2 py-1 text-[11px] text-fg-strong hover:border-border-strong"
      >
        <span className="text-faint">▾</span>
        <span className="max-w-[16rem] truncate">{triggerLabel}</span>
      </button>

      {open && (
        <div className="absolute left-0 z-20 mt-1 w-80 border border-border bg-bg shadow-lg">
          <ul className="max-h-72 overflow-y-auto">
            <li>
              <button
                onClick={() => select(null)}
                className={cn(
                  "flex w-full items-center justify-between px-3 py-2 text-left text-xs hover:bg-elevated",
                  selectedId === null ? "text-fg-strong" : "text-muted",
                )}
              >
                <span>{t.files.allSourcesRow}</span>
                <span className="tnum text-faint">
                  {roots.reduce((a, r) => a + r.file_count, 0)}
                </span>
              </button>
            </li>
            {roots.map((r) => (
              <li key={r.id} className="border-t border-surface-2">
                <div
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 text-xs",
                    selectedId === r.id && "bg-surface-2",
                  )}
                >
                  <button onClick={() => select(r.id)} className="min-w-0 flex-1 text-left">
                    <span className="block truncate text-fg-strong">{r.label || r.path}</span>
                    <span className="block text-[10px] text-faint">
                      {r.file_count} · {fmtDate(r.last_scanned_at)}
                      {r.missing_count > 0 && ` · ${t.sources.missingCount(r.missing_count)}`}
                    </span>
                  </button>
                  <button
                    onClick={() => onScanRoot(r.id)}
                    disabled={running}
                    aria-label={t.files.scanRootAria}
                    className="text-faint transition-colors hover:text-fg disabled:cursor-not-allowed disabled:opacity-40"
                  >⟳</button>
                  <button
                    onClick={() => onDelete(r.id)}
                    disabled={deletingId === r.id}
                    aria-label={t.sources.removeRoot}
                    className="text-faint transition-colors hover:text-danger disabled:cursor-not-allowed disabled:opacity-40"
                  >×</button>
                </div>
              </li>
            ))}
          </ul>
          <div className="border-t border-border p-3">
            <AddSource onAdded={onAdded} />
          </div>
        </div>
      )}
    </div>
  );
}
