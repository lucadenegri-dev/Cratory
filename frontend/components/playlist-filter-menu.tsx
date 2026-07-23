"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { Playlist } from "@/lib/api";
import { Button } from "@/components/ui";

/** Trigger + popover a checkbox per selezionare piu' playlist (filtro unione). */
export function PlaylistFilterMenu({ playlists, selected, onToggle, label }: {
  playlists: Playlist[];
  selected: Set<number>;
  onToggle: (id: number) => void;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <Button type="button" variant="outline" className="h-9 w-full justify-between" onClick={() => setOpen((o) => !o)}>
        <span className="truncate">{label}</span>
        <ChevronDown size={14} className="shrink-0" />
      </Button>
      {open && (
        <div className="absolute left-0 z-20 mt-1 max-h-60 w-full min-w-48 overflow-y-auto border border-border bg-elevated p-1 shadow-lg">
          {playlists.length === 0 && <p className="px-2 py-3 text-center text-xs text-muted">—</p>}
          {playlists.map((p) => (
            <label key={p.id} className="flex cursor-pointer items-center gap-2 px-2 py-1.5 text-sm hover:bg-surface">
              <input type="checkbox" checked={selected.has(p.id)} onChange={() => onToggle(p.id)} className="shrink-0" />
              <span className="min-w-0 flex-1 truncate">{p.name}</span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}
