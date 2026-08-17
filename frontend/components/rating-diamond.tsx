"use client";

import { useEffect, useRef, useState } from "react";

import { updateTrack } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

// Scala "calore" del voto: 1 oliva, 2 ambra, 3 terracotta (accento Cratory).
const RATING_COLORS: Record<number, string> = {
  1: "#8a8065",
  2: "#cfa14a",
  3: "#d8593f",
};

function Diamond({ value, size }: { value: number | null; size: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden>
      <polygon
        points="12,3 21,12 12,21 3,12"
        fill={value ? RATING_COLORS[value] : "none"}
        stroke={value ? "none" : "currentColor"}
        strokeWidth={1.5}
      />
    </svg>
  );
}

type Props = {
  trackId: number;
  rating: number | null;
  onSaved?: (rating: number | null) => void;
  size?: number;
  /** Dove si apre il selettore. `above` (default) per le righe di lista, dove
   *  il rombo vive sul bordo destro e sopra c'è sempre spazio; `right` per il
   *  dock, dove sopra c'è il seek e a destra la corsia è libera. */
  side?: "above" | "right";
};

export function RatingDiamond({ trackId, rating, onSaved, size = 18, side = "above" }: Props) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState<number | null>(rating);
  const rootRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setValue(rating);
  }, [rating]);

  // Aperto: click fuori o Esc chiudono senza votare.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const commit = async (next: number | null) => {
    const prev = value;
    setValue(next); // ottimistico
    setOpen(false);
    try {
      await updateTrack(trackId, { rating: next });
      onSaved?.(next);
    } catch {
      setValue(prev); // rollback
    }
  };

  return (
    <span ref={rootRef} className="relative inline-flex shrink-0 items-center">
      {/* Popup fuori dal flusso: l'espansione inline spostava gli elementi
          della riga. `right`: in fila accanto al rombo, centrato sulla sua
          altezza — i tre livelli si leggono come un seguito ordinato del
          controllo, non come un balloon appeso. */}
      {open && (
        <span className={cn(
          "absolute z-20 flex items-center gap-1 rounded-none border border-border bg-elevated px-1.5 py-1 shadow-lg",
          side === "right" ? "left-full top-1/2 ml-1.5 -translate-y-1/2" : "bottom-full right-0 mb-1",
        )}>
          {[1, 2, 3].map((level) => (
            <button
              key={level}
              type="button"
              title={t.tracks.ratingLevelTitle(level)}
              onClick={(e) => {
                e.stopPropagation();
                void commit(level === value ? null : level);
              }}
              className="shrink-0"
            >
              <Diamond value={level} size={size - 4} />
            </button>
          ))}
        </span>
      )}
      <button
        type="button"
        aria-label={t.tracks.ratingLabel}
        title={t.tracks.ratingLabel}
        onClick={(e) => {
          e.stopPropagation();
          setOpen((o) => !o);
        }}
        className="shrink-0 text-faint transition-colors hover:text-fg-strong"
      >
        <Diamond value={value} size={size} />
      </button>
    </span>
  );
}
