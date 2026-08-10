"use client";

import { useState } from "react";
import { coverThumbUrl, type Issue } from "@/lib/api";
import { CoverThumb } from "@/components/cover-thumb";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

export type GroupBy = "type" | "severity" | "none";

// Stessi campi retaggabili del backend (planner._EFFECTIVE_FIELDS).
const RETAGGABLE = new Set([
  "artist", "title", "album", "album_artist", "genre", "year", "label", "track_no", "comment",
]);

// Un'issue è "fixable" se ha un'azione applicabile: quarantena, svuotamento,
// o un campo retaggabile. Stessa logica usata nella riga (vedi IssueRow).
export function issueIsFixable(i: Issue): boolean {
  const action = i.suggested_fix_json?.action;
  if (action === "clear" || action === "quarantine") return true;
  return i.field != null && RETAGGABLE.has(i.field);
}

// Override "forte" (match sicuro da provider): la ConfBadge mappa high→strong.
// Riservato alle proposte di origine provider: le proposte AI (genre_review)
// sono per definizione "da rivedere", mai accettabili in blocco come un match
// sicuro — anche quando portano confidence "high" nel vocabolario dell'AI.
export function issueIsStrong(i: Issue): boolean {
  if (i.suggested_fix_json?.source !== "provider") return false;
  const c = i.suggested_fix_json?.confidence;
  return c === "high" || c === "strong";
}

const SEV_ORDER: Record<string, number> = { error: 0, warning: 1, info: 2 };

function SevMark({ sev }: { sev: string }) {
  if (sev === "error") return <span className="text-danger">▲</span>;
  if (sev === "warning") return <span className="text-warning">●</span>;
  return <span className="text-faint">·</span>;
}

function ConfBadge({ conf, source }: { conf: unknown; source: unknown }) {
  const t = useT();
  // normalizza il legacy: high->strong, text->weak. Il badge "strong" (verde,
  // "match sicuro da ID/tag vicini") è riservato ai provider: una proposta AI
  // con confidence "high" non è un match verificato, quindi scende a "medium"
  // per non far leggere come sicura un'ipotesi da rivedere.
  const isAi = source === "ai";
  const g = conf === "high" ? (isAi ? "medium" : "strong") : conf === "text" ? "weak" : conf;
  if (g !== "strong" && g !== "medium" && g !== "weak") return null;
  const cls =
    g === "strong" ? "border-ok text-ok"
    : g === "medium" ? "border-warning text-warning"
    : "border-border text-faint";
  const label =
    g === "strong" ? t.issues.confStrong
    : g === "medium" ? t.issues.confMedium
    : t.issues.confWeak;
  return (
    <span className={cn(
      "border px-1 py-0.5 text-[9px] uppercase tracking-wider", cls)}>
      {label}
    </span>
  );
}

function Cover({ fileId, dismissed }: { fileId: number; dismissed: boolean }) {
  const t = useT();
  const [zoom, setZoom] = useState(false);
  if (dismissed) return <span className="text-faint">{t.issues.coverNotApplied}</span>;
  return (
    <>
      <button type="button" onClick={() => setZoom(true)}
        className="block h-14 w-14 overflow-hidden border border-border transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-fg"
        title={t.issues.zoomTitle}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={coverThumbUrl(fileId)} alt="cover" className="h-full w-full object-cover" />
      </button>
      {zoom && (
        <div onClick={() => setZoom(false)}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-8">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={coverThumbUrl(fileId)} alt="cover"
               className="max-h-[80vh] max-w-[80vw] border border-border" />
        </div>
      )}
    </>
  );
}

function IssueRow({ issue, showSev, showType, onFix, onAccept, onDismiss, onReopen }: {
  issue: Issue;
  showSev: boolean;
  showType: boolean;
  onFix: (id: number, value: string) => Promise<void>;
  onAccept: (id: number) => Promise<void>;
  onDismiss: (id: number) => Promise<void>;
  onReopen: (id: number) => Promise<void>;
}) {
  const t = useT();
  const isCover = issue.type === "missing_cover";
  const fixable = issue.field != null && RETAGGABLE.has(issue.field);
  // Proposta di svuotamento (es. commento/titolo spazzatura): non c'è un valore
  // da digitare, si accetta "a vuoto".
  const isClear = issue.suggested_fix_json?.action === "clear";
  // File corrotto: la "fix" è mandarlo in quarantena, non ritaggarlo.
  const isQuarantine = issue.suggested_fix_json?.action === "quarantine";
  const suggested = typeof issue.suggested_fix_json?.to === "string"
    ? (issue.suggested_fix_json.to as string) : "";
  const conf = issue.suggested_fix_json?.confidence;
  const confSource = issue.suggested_fix_json?.source;
  const [value, setValue] = useState(suggested);
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  };

  return (
    <tr className={cn("border-b border-surface-2 last:border-0 hover:bg-surface", issue.status !== "open" && "opacity-70")}>
      {showSev && <td className="px-3 py-2 text-center align-top"><SevMark sev={issue.severity} /></td>}
      {showType && <td className="whitespace-nowrap px-3 py-2 align-top text-[11px] text-muted">{t.issues.typeLabel(issue.type)}</td>}
      <td className="px-3 py-2 align-top">
        <div className="flex items-start gap-2">
          <CoverThumb fileId={issue.file_id} />
          <div className="min-w-0">
            <div className="text-fg-strong">{issue.artist || t.common.empty}{issue.title ? ` — ${issue.title}` : ""}</div>
            <div className="max-w-[240px] truncate text-[10px] text-faint" title={issue.file_path}>{issue.file_path}</div>
          </div>
        </div>
      </td>
      <td className="px-3 py-2 align-top text-muted">{issue.field || t.common.empty}</td>
      <td className="px-3 py-2 align-top">
        {isCover ? (
          <Cover fileId={issue.file_id} dismissed={issue.status === "dismissed"} />
        ) : issue.status === "open" ? (
          isQuarantine ? (
            <span className="text-warning">{t.issues.fixQuarantine}</span>
          ) : isClear ? (
            <div className="flex items-center gap-1.5 text-[10px]">
              {issue.current_value && <span className="max-w-[200px] truncate text-faint line-through" title={issue.current_value}>{issue.current_value}</span>}
              <span className="text-faint">→</span>
              <span className="text-muted">{t.issues.emptyValueMark}</span>
            </div>
          ) : !fixable ? (
            <span className="text-faint">{t.issues.notFixable}</span>
          ) : (
            <div className="flex flex-col gap-1">
              {issue.current_value && (
                <div className="flex items-center gap-1.5 text-[10px]">
                  <span className="text-faint line-through">{issue.current_value}</span>
                  <span className="text-faint">→</span>
                </div>
              )}
              <input
                className="w-40 border border-border bg-bg px-2 py-1 text-[11px] text-fg-strong placeholder:text-faint focus:border-border-strong focus:outline-none"
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder={t.issues.writeField(issue.field ?? "")}
              />
            </div>
          )
        ) : issue.status === "accepted" ? (
          <span className="text-fg">{isQuarantine ? t.issues.fixQuarantine : (suggested || t.common.empty)}</span>
        ) : (
          <span className="text-faint" title={t.issues.dismissedTagUnchanged}>
            {issue.current_value ? `${issue.current_value} ${t.issues.unchangedSuffix}` : t.common.empty}
          </span>
        )}
      </td>
      <td className="px-3 py-2 align-top"><ConfBadge conf={conf} source={confSource} /></td>
      <td className="whitespace-nowrap px-3 py-2 align-top text-right">
        {issue.status === "open" ? (
          <span className="flex justify-end gap-1">
            {isCover || isClear || isQuarantine ? (
              <button disabled={busy}
                onClick={() => run(() => onAccept(issue.id))}
                className="border border-border px-2 py-0.5 text-[10px] text-ok hover:bg-elevated disabled:opacity-40"
              >{isClear ? t.issues.emptyShort : isQuarantine ? t.issues.quarantineShort : t.issues.acceptShort}</button>
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
          <span className="flex items-center justify-end gap-2">
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

// key stabile per riga: include il suggerimento così, quando l'AI lo imposta
// dopo il mount, la riga si rimonta e l'input mostra il valore.
function rowKey(i: Issue): string {
  const sug = typeof i.suggested_fix_json?.to === "string" ? i.suggested_fix_json.to : "";
  return `${i.id}:${sug}`;
}

export function IssuesTable({
  issues, groupBy, onFix, onAccept, onDismiss, onReopen, onAcceptGroup,
}: {
  issues: Issue[];
  groupBy: GroupBy;
  onFix: (id: number, value: string) => Promise<void>;
  onAccept: (id: number) => Promise<void>;
  onDismiss: (id: number) => Promise<void>;
  onReopen: (id: number) => Promise<void>;
  onAcceptGroup: (key: string) => Promise<void>;
}) {
  const t = useT();
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  const [groupBusy, setGroupBusy] = useState<string | null>(null);

  const showSev = groupBy !== "severity";
  const showType = groupBy !== "type";
  const colCount = 5 + (showSev ? 1 : 0) + (showType ? 1 : 0);

  const head = (
    <thead>
      <tr className="border-b border-border text-left text-[9px] uppercase tracking-wider text-faint">
        {showSev && <th className="px-3 py-2 text-center font-normal">!</th>}
        {showType && <th className="px-3 py-2 font-normal">{t.issues.colType}</th>}
        <th className="px-3 py-2 font-normal">{t.issues.colTrack}</th>
        <th className="px-3 py-2 font-normal">{t.issues.colField}</th>
        <th className="px-3 py-2 font-normal">{t.issues.colFix}</th>
        <th className="px-3 py-2 font-normal">{t.issues.colConf}</th>
        <th className="px-3 py-2 text-right font-normal">{t.issues.colActions}</th>
      </tr>
    </thead>
  );

  const rowFor = (i: Issue) => (
    <IssueRow key={rowKey(i)} issue={i} showSev={showSev} showType={showType}
      onFix={onFix} onAccept={onAccept} onDismiss={onDismiss} onReopen={onReopen} />
  );

  if (groupBy === "none") {
    return (
      <div className="overflow-x-auto border border-border">
        <table className="w-full border-collapse text-xs">
          {head}
          <tbody>{issues.map(rowFor)}</tbody>
        </table>
      </div>
    );
  }

  // Raggruppa preservando l'ordine d'inserimento dei gruppi.
  const groups = new Map<string, Issue[]>();
  for (const i of issues) {
    const key = groupBy === "type" ? i.type : i.severity;
    (groups.get(key) ?? groups.set(key, []).get(key)!).push(i);
  }
  const entries = [...groups.entries()].sort((a, b) =>
    groupBy === "severity"
      ? (SEV_ORDER[a[0]] ?? 9) - (SEV_ORDER[b[0]] ?? 9)
      : b[1].length - a[1].length,
  );

  const labelFor = (key: string) =>
    groupBy === "type" ? t.issues.typeLabel(key) : key;

  const toggle = (key: string) =>
    setCollapsed((cur) => {
      const next = new Set(cur);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });

  const acceptGroup = async (key: string) => {
    setGroupBusy(key);
    try { await onAcceptGroup(key); } finally { setGroupBusy(null); }
  };

  return (
    <div className="overflow-x-auto border border-border">
      <table className="w-full border-collapse text-xs">
        {head}
        {entries.map(([key, list]) => {
          const isOpen = !collapsed.has(key);
          const open = list.filter((i) => i.status === "open").length;
          return (
            <tbody key={key} className="border-t border-border first:border-t-0">
              <tr className="bg-surface-2">
                <td colSpan={colCount} className="px-3 py-2">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => toggle(key)}
                      className="flex items-center gap-2 text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-fg"
                      aria-expanded={isOpen}
                    >
                      <span className="w-3 text-faint">{isOpen ? "▾" : "▸"}</span>
                      {groupBy === "severity" && <SevMark sev={key} />}
                      <span className="text-[11px] font-semibold uppercase tracking-wider text-fg-strong">
                        {labelFor(key)}
                      </span>
                      <span className="tnum text-[10px] text-muted">{t.issues.groupMeta(open, list.length)}</span>
                    </button>
                    {open > 0 && (
                      <button
                        type="button"
                        disabled={groupBusy === key}
                        onClick={() => acceptGroup(key)}
                        className="ml-auto border border-border px-2 py-0.5 text-[10px] text-ok hover:bg-elevated disabled:opacity-40"
                      >{t.issues.groupAccept}</button>
                    )}
                  </div>
                </td>
              </tr>
              {isOpen && list.map(rowFor)}
            </tbody>
          );
        })}
      </table>
    </div>
  );
}
