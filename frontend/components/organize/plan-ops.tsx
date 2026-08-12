"use client";

import { coverThumbUrl, type PlanOp } from "@/lib/organize/api";
import { CoverThumb } from "@/components/organize/cover-thumb";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/organize/i18n";
import type { Dictionary } from "@/lib/organize/i18n";

const GROUP_KINDS = ["RETAG", "COVER", "RATING", "RENAME", "MOVE", "DELETE"] as const;

function groupLabel(t: Dictionary, kind: (typeof GROUP_KINDS)[number]): string {
  switch (kind) {
    case "RETAG": return t.plan.groupRetag;
    case "COVER": return t.plan.groupCover;
    case "RATING": return t.plan.groupRating;
    case "RENAME": return t.plan.groupRename;
    case "MOVE": return t.plan.groupMove;
    case "DELETE": return t.plan.groupDelete;
  }
}

function basename(p: string): string {
  const i = p.lastIndexOf("/");
  return i >= 0 ? p.slice(i + 1) : p;
}

function OpRow({ op }: { op: PlanOp }) {
  const t = useT();
  const isDelete = op.kind === "DELETE";
  return (
    <div className={cn("flex items-center gap-3 border border-t-0 border-surface-2 px-3 py-1.5 first:border-t",
      isDelete ? "border-l-2 border-l-danger" : "border-l-2 border-l-border",
      op.skipped && "opacity-50")}>
      {/* Sui COVER l'unica cover reale è quella già mostrata al centro della riga
          (la proposta da embeddare): il planner emette COVER solo per file senza
          artwork (planner.py, has_cover è False), quindi qui a sinistra cadrebbe
          comunque sulla stessa proposta — due copie della stessa immagine, la
          seconda senza tratteggio, che si legge come "artwork già nel file". */}
      <CoverThumb fileId={op.file_id} source={op.kind === "COVER" ? null : undefined} />
      {op.skipped && (
        <span className="shrink-0 text-[9px] uppercase tracking-wider text-warning">{t.plan.skip}</span>
      )}
      <span className="min-w-[200px] max-w-[200px] truncate text-[11px] text-muted" title={op.file_path}>{basename(op.file_path)}</span>
      <span className="flex items-center gap-2 text-[11px]">
        {op.kind === "COVER" ? (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={coverThumbUrl(op.file_id)} alt="cover"
                 className="h-8 w-8 border border-border object-cover" />
            <span className="text-fg-strong">{t.plan.embedCover}</span>
            <span className="text-faint">({String(op.after.source ?? "")})</span>
          </>
        ) : op.kind === "RETAG" ? (
          Object.keys(op.after).map((f, i) => (
            <span key={f}>
              {i > 0 ? " · " : ""}{f}: <span className="text-faint">{String(op.before[f] ?? t.common.empty)}</span>
              {" → "}<span className="text-fg-strong">{String(op.after[f] ?? t.common.empty)}</span>
            </span>
          ))
        ) : op.kind === "RATING" ? (
          <span className="text-fg-strong">{t.plan.clearRating}</span>
        ) : isDelete ? (
          <span><span className="text-faint">→</span> <span className="text-warning">{t.plan.quarantine}</span></span>
        ) : (
          <span><span className="text-faint">→</span> <span className="text-fg-strong">{String(op.after.path ?? "")}</span></span>
        )}
      </span>
    </div>
  );
}

export function PlanOps({ ops }: { ops: PlanOp[] }) {
  const t = useT();
  return (
    <div className="flex flex-col gap-5">
      {GROUP_KINDS.map((kind) => {
        const group = ops.filter((o) => o.kind === kind);
        if (group.length === 0) return null;
        return (
          <div key={kind}>
            <div className="mb-2 text-[11px] uppercase tracking-wider text-fg-strong">
              {groupLabel(t, kind)} <span className="text-muted">· {group.length}</span>
            </div>
            <div className="flex flex-col">{group.map((o) => <OpRow key={o.id} op={o} />)}</div>
          </div>
        );
      })}
    </div>
  );
}
