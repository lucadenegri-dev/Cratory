import Link from "next/link";

export type MiniBarRow = { label: string; value: number; href?: string };

/** Lista etichetta → barra orizzontale → valore. Riusata per Camelot e etichette. */
export function MiniBars({ rows }: { rows: MiniBarRow[] }) {
  if (rows.length === 0) return <p className="text-sm text-faint">—</p>;
  const max = Math.max(...rows.map((r) => r.value), 1);
  return (
    <div className="space-y-1.5">
      {rows.map((r) => {
        const body = (
          <>
            <span className="w-20 shrink-0 truncate text-xs text-muted group-hover:text-fg" title={r.label}>{r.label}</span>
            <span className="h-2 flex-1 overflow-hidden bg-elevated">
              <span className="block h-full bg-fg" style={{ width: `${Math.max(6, Math.round((r.value / max) * 100))}%` }} />
            </span>
            <span className="tnum w-6 shrink-0 text-right text-xs text-muted">{r.value}</span>
          </>
        );
        return r.href ? (
          <Link key={r.label} href={r.href} className="group flex items-center gap-2">{body}</Link>
        ) : (
          <div key={r.label} className="group flex items-center gap-2">{body}</div>
        );
      })}
    </div>
  );
}
