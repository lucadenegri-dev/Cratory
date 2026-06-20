"use client";

// Colorazione tonalità in stile Mixed In Key / Camelot wheel.
// Le key armonicamente compatibili (numeri adiacenti sulla ruota) hanno colori
// adiacenti; A e B dello stesso numero condividono la tinta. I colori NON vengono
// mai inventati per una key assente: in quel caso si mostra un trattino neutro.

const CAMELOT_COLOR: Record<number, string> = {
  1: "#3ad6c4",  // teal
  2: "#5cd98a",  // verde
  3: "#94dd66",  // verde-lime
  4: "#d8cf86",  // giallo-cachi
  5: "#e8b96a",  // oro
  6: "#e89a86",  // corallo
  7: "#e87ab0",  // magenta-rosa
  8: "#ef7a9c",  // rosa
  9: "#b596ea",  // lavanda
  10: "#8fa6ef", // pervinca
  11: "#74c2ee", // azzurro
  12: "#4fd9d0", // ciano
};

const CAMELOT_RE = /^\s*(\d{1,2})\s*([ABab])\s*$/;

export function KeyBadge({ camelot, className }: { camelot: string | null; className?: string }) {
  const m = camelot ? CAMELOT_RE.exec(camelot) : null;
  const number = m ? Number(m[1]) : null;
  const color = number && number >= 1 && number <= 12 ? CAMELOT_COLOR[number] : null;

  if (!m || !color) {
    return <span className={`text-faint ${className ?? ""}`}>{camelot ?? "—"}</span>;
  }

  const label = `${m[1]}${m[2].toUpperCase()}`;
  return (
    <span
      className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-xs font-semibold tnum ${className ?? ""}`}
      style={{ backgroundColor: color, color: "#10121a" }}
    >
      {label}
    </span>
  );
}
