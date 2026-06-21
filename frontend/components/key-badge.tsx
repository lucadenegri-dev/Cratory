// Camelot key reso in monocromatico: nessuna tinta inventata.
// Chiave assente o non valida → trattino neutro.

const CAMELOT_RE = /^\s*(\d{1,2})\s*([ABab])\s*$/;

export function KeyBadge({ camelot, className }: { camelot: string | null; className?: string }) {
  const m = camelot ? CAMELOT_RE.exec(camelot) : null;
  const number = m ? Number(m[1]) : null;

  if (!m || number == null || number < 1 || number > 12) {
    return <span className={`text-faint ${className ?? ""}`}>{camelot ?? "—"}</span>;
  }

  const label = `${m[1]}${m[2].toUpperCase()}`;
  return <span className={`tnum font-medium text-fg-strong ${className ?? ""}`}>{label}</span>;
}
