"use client";

import { fmtDuration, type FileRow, type FileQuery } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";
import { CoverThumb } from "@/components/cover-thumb";

type SortKey = NonNullable<FileQuery["sort"]>;
type SortDir = NonNullable<FileQuery["dir"]>;

// intestazione ordinabile: click imposta la colonna (asc) o inverte se già attiva
function SortHead({
  label, col, sort, dir, onSort, align = "left",
}: {
  label: string;
  col: SortKey;
  sort: SortKey;
  dir: SortDir;
  onSort: (col: SortKey) => void;
  align?: "left" | "right" | "center";
}) {
  const active = sort === col;
  const justify = align === "right" ? "justify-end" : align === "center" ? "justify-center" : "justify-start";
  return (
    <th className={cn("px-3 py-2 font-normal", align === "right" && "text-right", align === "center" && "text-center")}>
      <button
        onClick={() => onSort(col)}
        className={cn("inline-flex items-center gap-1 uppercase tracking-wider hover:text-fg", justify, active ? "text-fg" : "text-faint")}
      >
        <span>{label}</span>
        <span className="text-[8px]">{active ? (dir === "desc" ? "▼" : "▲") : ""}</span>
      </button>
    </th>
  );
}

function Indicator({ row }: { row: FileRow }) {
  const t = useT();
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
      {row.in_dup_group && <span className="text-muted" title={t.files.dupTitle}>⧉</span>}
    </span>
  );
}

export function FilesTable({
  rows, sort, dir, onSort,
}: {
  rows: FileRow[];
  sort: SortKey;
  dir: SortDir;
  onSort: (col: SortKey) => void;
}) {
  const headProps = { sort, dir, onSort };
  return (
    <div className="overflow-x-auto border border-border">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-border text-left text-[9px]">
            <th className="w-8 px-3 py-2" aria-label="cover" />
            <SortHead label="Path" col="path" {...headProps} />
            <SortHead label="Artist" col="artist" {...headProps} />
            <SortHead label="Title" col="title" {...headProps} />
            <SortHead label="Fmt" col="ext" {...headProps} />
            <SortHead label="Kbps" col="bitrate" align="right" {...headProps} />
            <SortHead label="Dur" col="duration" align="right" {...headProps} />
            <th className="px-3 py-2 text-center font-normal text-[9px] uppercase tracking-wider text-faint">!</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b border-surface-2 last:border-0 hover:bg-surface">
              <td className="py-1 pl-3 pr-0">
                <CoverThumb fileId={r.id} source={r.cover_source} />
              </td>
              <td className="max-w-[300px] px-3 py-1 text-muted" title={r.path}>
                {/* U+200E (LRM) prima del path: dir=rtl porta l'ellissi in testa,
                    ma senza un carattere forte LTR iniziale lo "/" di apertura è
                    neutro e il bidi lo sposta in coda alla riga. */}
                <span dir="rtl" className="block truncate text-left">{"‎" + r.path}</span>
              </td>
              <td className="px-3 py-1 text-fg">{r.artist || <span className="text-faint">—</span>}</td>
              <td className="px-3 py-1 text-fg-strong">{r.title || <span className="text-faint">—</span>}</td>
              <td className="px-3 py-1 uppercase text-muted">{r.ext}</td>
              <td className="tnum px-3 py-1 text-right text-fg">{r.bitrate ?? "—"}</td>
              <td className="tnum px-3 py-1 text-right text-fg">{fmtDuration(r.duration_s)}</td>
              <td className="px-3 py-1 text-center"><Indicator row={r} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
