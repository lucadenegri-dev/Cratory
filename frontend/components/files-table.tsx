"use client";

import { fmtDuration, type FileRow } from "@/lib/api";
import { cn } from "@/lib/cn";

function Indicator({ row }: { row: FileRow }) {
  const sev = row.worst_severity;
  return (
    <span className="inline-flex items-center justify-center gap-1">
      {row.issue_count > 0 ? (
        <span
          className={cn(
            "tnum",
            sev === "error" ? "text-danger" : sev === "warning" ? "text-warning" : "text-muted",
          )}
        >
          {sev === "error" ? "▲" : "●"}{row.issue_count}
        </span>
      ) : !row.in_dup_group ? (
        <span className="text-faint">·</span>
      ) : null}
      {row.in_dup_group && <span className="text-muted" title="doppione">⧉</span>}
    </span>
  );
}

export function FilesTable({ rows }: { rows: FileRow[] }) {
  return (
    <div className="overflow-x-auto border border-border">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-border text-left text-[9px] uppercase tracking-wider text-faint">
            <th className="px-3 py-2 font-normal">Path</th>
            <th className="px-3 py-2 font-normal">Artist</th>
            <th className="px-3 py-2 font-normal">Title</th>
            <th className="px-3 py-2 font-normal">Fmt</th>
            <th className="px-3 py-2 text-right font-normal">Kbps</th>
            <th className="px-3 py-2 text-right font-normal">Dur</th>
            <th className="px-3 py-2 text-center font-normal">!</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-surface-2 last:border-0 hover:bg-surface">
              <td className="max-w-[260px] truncate px-3 py-1.5 text-muted" title={r.path}>{r.path}</td>
              <td className="px-3 py-1.5 text-fg">{r.artist || <span className="text-faint">—</span>}</td>
              <td className="px-3 py-1.5 text-fg-strong">{r.title || <span className="text-faint">—</span>}</td>
              <td className="px-3 py-1.5 uppercase text-muted">{r.ext}</td>
              <td className="tnum px-3 py-1.5 text-right text-fg">{r.bitrate ?? "—"}</td>
              <td className="tnum px-3 py-1.5 text-right text-fg">{fmtDuration(r.duration_s)}</td>
              <td className="px-3 py-1.5 text-center"><Indicator row={r} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
