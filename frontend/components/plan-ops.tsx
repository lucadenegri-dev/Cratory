"use client";

import { coverThumbUrl, type PlanOp } from "@/lib/api";
import { cn } from "@/lib/cn";

const GROUPS: { kind: string; label: string }[] = [
  { kind: "RETAG", label: "Retag" },
  { kind: "COVER", label: "Copertina" },
  { kind: "RENAME", label: "Rinomina" },
  { kind: "MOVE", label: "Sposta" },
  { kind: "DELETE", label: "Elimina" },
];

function basename(p: string): string {
  const i = p.lastIndexOf("/");
  return i >= 0 ? p.slice(i + 1) : p;
}

function OpRow({ op }: { op: PlanOp }) {
  const isDelete = op.kind === "DELETE";
  return (
    <div className={cn("flex items-baseline gap-3 border border-t-0 border-surface-2 px-3 py-1.5 first:border-t",
      isDelete ? "border-l-2 border-l-danger" : "border-l-2 border-l-border",
      op.skipped && "opacity-50")}>
      {op.skipped && (
        <span className="shrink-0 text-[9px] uppercase tracking-wider text-warning">salta</span>
      )}
      <span className="min-w-[200px] max-w-[200px] truncate text-[11px] text-muted" title={op.file_path}>{basename(op.file_path)}</span>
      <span className="flex items-center gap-2 text-[11px]">
        {op.kind === "COVER" ? (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={coverThumbUrl(op.file_id)} alt="cover"
                 className="h-8 w-8 border border-border object-cover" />
            <span className="text-fg-strong">embed copertina</span>
            <span className="text-faint">({String(op.after.source ?? "")})</span>
          </>
        ) : op.kind === "RETAG" ? (
          Object.keys(op.after).map((f, i) => (
            <span key={f}>
              {i > 0 ? " · " : ""}{f}: <span className="text-faint">{String(op.before[f] ?? "—")}</span>
              {" → "}<span className="text-fg-strong">{String(op.after[f] ?? "—")}</span>
            </span>
          ))
        ) : isDelete ? (
          <span><span className="text-faint">→</span> <span className="text-warning">quarantena</span></span>
        ) : (
          <span><span className="text-faint">→</span> <span className="text-fg-strong">{String(op.after.path ?? "")}</span></span>
        )}
      </span>
    </div>
  );
}

export function PlanOps({ ops }: { ops: PlanOp[] }) {
  return (
    <div className="flex flex-col gap-5">
      {GROUPS.map(({ kind, label }) => {
        const group = ops.filter((o) => o.kind === kind);
        if (group.length === 0) return null;
        return (
          <div key={kind}>
            <div className="mb-2 text-[11px] uppercase tracking-wider text-fg-strong">
              {label} <span className="text-muted">· {group.length}</span>
            </div>
            <div className="flex flex-col">{group.map((o) => <OpRow key={o.id} op={o} />)}</div>
          </div>
        );
      })}
    </div>
  );
}
