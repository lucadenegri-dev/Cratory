"use client";

import { useState } from "react";
import { coverThumbUrl, type Issue } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

// Stessi campi retaggabili del backend (planner._EFFECTIVE_FIELDS).
const RETAGGABLE = new Set([
  "artist", "title", "album", "album_artist", "genre", "year", "label", "track_no", "comment",
]);

function SevMark({ sev }: { sev: string }) {
  if (sev === "error") return <span className="text-danger">▲</span>;
  if (sev === "warning") return <span className="text-warning">●</span>;
  return <span className="text-faint">·</span>;
}

function ConfBadge({ conf }: { conf: unknown }) {
  const t = useT();
  if (conf !== "high" && conf !== "text") return null;
  const high = conf === "high";
  return (
    <span className={cn(
      "border px-1 py-0.5 text-[9px] uppercase tracking-wider",
      high ? "border-ok text-ok" : "border-warning text-warning")}>
      {high ? t.issues.confHigh : t.issues.confText}
    </span>
  );
}

function IssueRow({ issue, onFix, onAccept, onDismiss, onReopen }: {
  issue: Issue;
  onFix: (id: number, value: string) => Promise<void>;
  onAccept: (id: number) => Promise<void>;
  onDismiss: (id: number) => Promise<void>;
  onReopen: (id: number) => Promise<void>;
}) {
  const t = useT();
  const isCover = issue.type === "missing_cover";
  const [zoom, setZoom] = useState(false);
  const fixable = issue.field != null && RETAGGABLE.has(issue.field);
  const suggested = typeof issue.suggested_fix_json?.to === "string"
    ? (issue.suggested_fix_json.to as string) : "";
  const conf = issue.suggested_fix_json?.confidence;
  const [value, setValue] = useState(suggested);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  };

  return (
    <tr className={cn("border-b border-surface-2 last:border-0 hover:bg-surface", issue.status !== "open" && "opacity-70")}>
      <td className="px-3 py-2 text-center"><SevMark sev={issue.severity} /></td>
      <td className="whitespace-nowrap px-3 py-2 text-fg">{issue.type}</td>
      <td className="px-3 py-2">
        <div className="text-fg-strong">{issue.artist || t.common.empty}{issue.title ? ` — ${issue.title}` : ""}</div>
        <div className="max-w-[220px] truncate text-[10px] text-faint" title={issue.file_path}>{issue.file_path}</div>
      </td>
      <td className="px-3 py-2 text-muted">{issue.field || t.common.empty}</td>
      <td className="px-3 py-2">
        {isCover ? (
          issue.status === "dismissed" ? (
            <span className="text-faint">{t.issues.coverNotApplied}</span>
          ) : (
            <button type="button" onClick={() => setZoom(true)}
              className="block h-11 w-11 overflow-hidden border border-border hover:border-border-strong"
              title={t.issues.zoomTitle}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={coverThumbUrl(issue.file_id)} alt="cover"
                   className="h-full w-full object-cover" />
            </button>
          )
        ) : issue.status === "open" ? (
          fixable ? (
            <div className="flex flex-col gap-1">
              {issue.current_value && (
                <div className="flex items-center gap-1.5 text-[10px]">
                  <span className="text-faint line-through">{issue.current_value}</span>
                  <span className="text-faint">→</span>
                </div>
              )}
              <input
                className="w-36 border border-border bg-bg px-2 py-1 text-[11px] text-fg-strong placeholder:text-faint focus:border-border-strong focus:outline-none"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={t.issues.writeField(issue.field ?? "")}
              />
            </div>
          ) : (
            <span className="text-faint">{t.issues.notFixable}</span>
          )
        ) : issue.status === "accepted" ? (
          <span className="text-fg">{suggested || t.common.empty}</span>
        ) : (
          <span className="text-faint" title={t.issues.dismissedTagUnchanged}>
            {issue.current_value ? `${issue.current_value} ${t.issues.unchangedSuffix}` : t.common.empty}
          </span>
        )}
        {zoom && (
          <div onClick={() => setZoom(false)}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-8">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={coverThumbUrl(issue.file_id)} alt="cover"
                 className="max-h-[80vh] max-w-[80vw] border border-border" />
          </div>
        )}
      </td>
      <td className="px-3 py-2"><ConfBadge conf={conf} /></td>
      <td className="whitespace-nowrap px-3 py-2">
        {issue.status === "open" ? (
          <span className="flex gap-1">
            {isCover ? (
              <button disabled={busy}
                onClick={() => run(() => onAccept(issue.id))}
                className="border border-border px-2 py-0.5 text-[10px] text-ok hover:bg-elevated disabled:opacity-40"
              >{t.issues.acceptShort}</button>
            ) : fixable && (
              <button
                disabled={busy || !value.trim()}
                onClick={() => run(() => onFix(issue.id, value.trim()))}
                className="border border-border px-2 py-0.5 text-[10px] text-ok hover:bg-elevated disabled:opacity-40"
              >{t.issues.acceptShort}</button>
            )}
            <button
              disabled={busy}
              onClick={() => run(() => onDismiss(issue.id))}
              className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
            >{t.issues.dismissShort}</button>
          </span>
        ) : (
          <span className="flex items-center gap-2">
            <span className={cn("border px-1.5 py-0.5 text-[9px] uppercase tracking-wider",
              issue.status === "accepted" ? "border-border text-ok" : "border-border text-faint")}>
              {issue.status === "accepted" ? t.issues.badgeAccepted : t.issues.badgeDismissed}
            </span>
            <button disabled={busy} onClick={() => run(() => onReopen(issue.id))}
              className="text-faint hover:text-fg disabled:opacity-40" title={t.issues.reopenTitle}>↺</button>
          </span>
        )}
      </td>
    </tr>
  );
}

export function IssuesTable({ issues, onFix, onAccept, onDismiss, onReopen }: {
  issues: Issue[];
  onFix: (id: number, value: string) => Promise<void>;
  onAccept: (id: number) => Promise<void>;
  onDismiss: (id: number) => Promise<void>;
  onReopen: (id: number) => Promise<void>;
}) {
  const t = useT();
  return (
    <div className="overflow-x-auto border border-border">
      <table className="w-full border-collapse text-xs">
        <thead>
          <tr className="border-b border-border text-left text-[9px] uppercase tracking-wider text-faint">
            <th className="px-3 py-2 text-center font-normal">!</th>
            <th className="px-3 py-2 font-normal">{t.issues.colType}</th>
            <th className="px-3 py-2 font-normal">{t.issues.colTrack}</th>
            <th className="px-3 py-2 font-normal">{t.issues.colField}</th>
            <th className="px-3 py-2 font-normal">{t.issues.colFix}</th>
            <th className="px-3 py-2 font-normal">{t.issues.colConf}</th>
            <th className="px-3 py-2 font-normal">{t.issues.colActions}</th>
          </tr>
        </thead>
        <tbody>
          {issues.map((i) => {
            // La key include il suggerimento: quando l'AI lo imposta dopo il mount,
            // la riga si rimonta e l'input mostra il valore (useState si re-inizializza).
            const sug = typeof i.suggested_fix_json?.to === "string" ? i.suggested_fix_json.to : "";
            return (
              <IssueRow key={`${i.id}:${sug}`} issue={i}
                onFix={onFix} onAccept={onAccept} onDismiss={onDismiss} onReopen={onReopen} />
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
