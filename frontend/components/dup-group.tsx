"use client";

import { useState } from "react";
import { fmtDuration, type DupGroup } from "@/lib/api";
import { cn } from "@/lib/cn";

export function DupGroupCard({ group, onSetKeeper, onDismiss }: {
  group: DupGroup;
  onSetKeeper: (groupId: number, fileId: number) => Promise<void>;
  onDismiss: (groupId: number) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  };
  const dismissed = group.dismissed;

  return (
    <div className={cn("border border-border", dismissed && "opacity-60")}>
      <div className="flex items-center justify-between border-b border-border bg-surface-2 px-3 py-1.5">
        <span className="text-[10px] tracking-wider text-muted">
          GRUPPO #{group.id} · match: <span className="text-fg-strong">{group.match_kind}</span>
          {dismissed && <span className="text-faint"> · scartato</span>}
        </span>
        {dismissed ? (
          <button
            disabled={busy}
            onClick={() => run(() => onSetKeeper(group.id, group.keeper_file_id))}
            className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
          >↺ ripristina</button>
        ) : (
          <button
            disabled={busy}
            onClick={() => run(() => onDismiss(group.id))}
            className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
          >non è un doppione</button>
        )}
      </div>
      <div>
        {group.members.map((m) => {
          const isKeeper = !dismissed && m.file_id === group.keeper_file_id;
          const isRemove = !dismissed && !isKeeper;
          return (
            <div
              key={m.file_id}
              onClick={isRemove && !busy ? () => run(() => onSetKeeper(group.id, m.file_id)) : undefined}
              title={isRemove ? "rendi questo il keeper" : undefined}
              className={cn(
                "grid grid-cols-[64px_1fr_auto] items-center gap-3 border-b border-surface-2 px-3 py-1.5 last:border-0",
                isKeeper && "border-l-2 border-l-ok bg-surface",
                isRemove && "cursor-pointer hover:bg-surface",
              )}
            >
              <span className={cn("border px-1.5 py-0.5 text-center text-[9px] tracking-wider",
                isKeeper ? "border-ok text-ok" : "border-border text-muted")}>
                {isKeeper ? "KEEP" : isRemove ? "REMOVE" : "—"}
              </span>
              <span className={cn("truncate text-[11px]", isKeeper ? "text-fg-strong" : "text-muted")} title={m.path}>{m.path}</span>
              <span className="flex items-center gap-3 text-[10px] text-muted">
                <span className="uppercase">{m.ext}</span>
                <span className="tnum w-10 text-right">{m.bitrate ?? "—"}</span>
                <span className="tnum w-9 text-right">{fmtDuration(m.duration_s)}</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
