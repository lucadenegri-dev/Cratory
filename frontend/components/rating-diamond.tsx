"use client";

import { useEffect, useRef, useState } from "react";

import { updateTrack } from "@/lib/api";
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
};

export function RatingDiamond({ trackId, rating, onSaved, size = 18 }: Props) {
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
    <span ref={rootRef} className="inline-flex shrink-0 items-center gap-0.5">
      {open &&
        [1, 2, 3].map((level) => (
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
