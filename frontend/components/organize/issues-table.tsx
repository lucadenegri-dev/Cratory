"use client";

import { useState } from "react";
import { coverThumbUrl, type Issue } from "@/lib/organize/api";
import { CoverThumb } from "@/components/organize/cover-thumb";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

import {
  issueIsFixable, issueIsStrong, RETAGGABLE, suggestedValue,
  type Drafts, type GroupBy,
} from "@/lib/organize/issue-actions";

export { issueIsFixable, issueIsStrong, type GroupBy };

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
    g === "strong" ? t.organize.issues.confStrong
    : g === "medium" ? t.organize.issues.confMedium
    : t.organize.issues.confWeak;
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
  if (dismissed) return <span className="text-faint">{t.organize.issues.coverNotApplied}</span>;
  return (
    <>
      <button type="button" onClick={() => setZoom(true)}
        className="block h-14 w-14 overflow-hidden border border-border transition-colors hover:border-border-strong focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-fg"
        title={t.organize.issues.zoomTitle}>
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

function IssueRow({ issue, showSev, showType, draft, onDraft, onFix, onAccept, onDismiss, onReopen }: {
  issue: Issue;
  showSev: boolean;
  showType: boolean;
  /** Valore digitato a mano (se c'è): la bozza vive nella pagina, non qui,
   *  così i comandi massivi la vedono. */
  draft: string | undefined;
  onDraft: (id: number, value: string) => void;
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
  const suggested = suggestedValue(issue);
  const conf = issue.suggested_fix_json?.confidence;
  const confSource = issue.suggested_fix_json?.source;
  // Derivato, non stato locale: senza bozza mostra il suggerimento, anche
  // quando l'AI/provider lo imposta dopo il mount (niente rimontaggio).
  const value = draft ?? suggested;
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try { await fn(); } finally { setBusy(false); }
  };

  return (
    <tr className={cn("border-b border-surface-2 last:border-0 hover:bg-surface", issue.status !== "open" && "opacity-70")}>
      {showSev && <td className="px-3 py-2 text-center align-top"><SevMark sev={issue.severity} /></td>}
      {showType && <td className="whitespace-nowrap px-3 py-2 align-top text-[11px] text-muted">{t.organize.issues.typeLabel(issue.type)}</td>}
      <td className="px-3 py-2 align-top">
        <div className="flex items-start gap-2">
          <CoverThumb fileId={issue.file_id} />
          <div className="min-w-0">
            <div className="text-fg-strong">{issue.artist || t.organize.common.empty}{issue.title ? ` — ${issue.title}` : ""}</div>
            <div className="max-w-[240px] truncate text-[10px] text-faint" title={issue.file_path}>{issue.file_path}</div>
          </div>
        </div>
      </td>
      <td className="px-3 py-2 align-top text-muted">{issue.field || t.organize.common.empty}</td>
      <td className="px-3 py-2 align-top">
        {isCover ? (
          <Cover fileId={issue.file_id} dismissed={issue.status === "dismissed"} />
        ) : issue.status === "open" ? (
          isQuarantine ? (
            <span className="text-warning">{t.organize.issues.fixQuarantine}</span>
          ) : isClear ? (
            <div className="flex items-center gap-1.5 text-[10px]">
              {issue.current_value && <span className="max-w-[200px] truncate text-faint line-through" title={issue.current_value}>{issue.current_value}</span>}
              <span className="text-faint">→</span>
              <span className="text-muted">{t.organize.issues.emptyValueMark}</span>
            </div>
          ) : !fixable ? (
            <span className="text-faint">{t.organize.issues.notFixable}</span>
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
                onChange={(e) => onDraft(issue.id, e.target.value)}
                placeholder={t.organize.issues.writeField(issue.field ?? "")}
              />
            </div>
          )
        ) : issue.status === "accepted" ? (
          <span className="text-fg">{isQuarantine ? t.organize.issues.fixQuarantine : (suggested || t.organize.common.empty)}</span>
        ) : (
          <span className="text-faint" title={t.organize.issues.dismissedTagUnchanged}>
            {issue.current_value ? `${issue.current_value} ${t.organize.issues.unchangedSuffix}` : t.organize.common.empty}
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
              >{isClear ? t.organize.issues.emptyShort : isQuarantine ? t.organize.issues.quarantineShort : t.organize.issues.acceptShort}</button>
            ) : fixable && (
              <button
                disabled={busy || !value.trim()}
                onClick={() => run(() => onFix(issue.id, value.trim()))}
                className="border border-border px-2 py-0.5 text-[10px] text-ok hover:bg-elevated disabled:opacity-40"
              >{t.organize.issues.acceptShort}</button>
            )}
            <button
              disabled={busy}
              onClick={() => run(() => onDismiss(issue.id))}
              className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
            >{t.organize.issues.dismissShort}</button>
          </span>
        ) : (
          <span className="flex items-center justify-end gap-2">
            <span className={cn("border px-1.5 py-0.5 text-[9px] uppercase tracking-wider",
              issue.status === "accepted" ? "border-border text-ok" : "border-border text-faint")}>
              {issue.status === "accepted" ? t.organize.issues.badgeAccepted : t.organize.issues.badgeDismissed}
            </span>
            <button disabled={busy} onClick={() => run(() => onReopen(issue.id))}
              className="text-faint hover:text-fg disabled:opacity-40" title={t.organize.issues.reopenTitle}>↺</button>
          </span>
        )}
      </td>
    </tr>
  );
}

export function IssuesTable({
  issues, groupBy, rank, drafts, onDraft, onFix, onAccept, onDismiss, onReopen,
  onAcceptGroup, onDismissGroup,
}: {
  issues: Issue[];
  groupBy: GroupBy;
  /** Rango di un gruppo (vedi groupOrder): calcolato dalla pagina su TUTTE le
   *  issue, così accettare una riga non fa scavalcare i gruppi. */
  rank: (key: string) => number;
  drafts: Drafts;
  onDraft: (id: number, value: string) => void;
  onFix: (id: number, value: string) => Promise<void>;
  onAccept: (id: number) => Promise<void>;
  onDismiss: (id: number) => Promise<void>;
  onReopen: (id: number) => Promise<void>;
  /** Ricevono le issue del gruppo (aperte e non): la pagina decide cosa farne. */
  onAcceptGroup: (list: Issue[]) => Promise<void>;
  onDismissGroup: (list: Issue[]) => Promise<void>;
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
        {showType && <th className="px-3 py-2 font-normal">{t.organize.issues.colType}</th>}
        <th className="px-3 py-2 font-normal">{t.organize.issues.colTrack}</th>
        <th className="px-3 py-2 font-normal">{t.organize.issues.colField}</th>
        <th className="px-3 py-2 font-normal">{t.organize.issues.colFix}</th>
        <th className="px-3 py-2 font-normal">{t.organize.issues.colConf}</th>
        <th className="px-3 py-2 text-right font-normal">{t.organize.issues.colActions}</th>
      </tr>
    </thead>
  );

  const rowFor = (i: Issue) => (
    <IssueRow key={i.id} issue={i} showSev={showSev} showType={showType}
      draft={drafts[i.id]} onDraft={onDraft}
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
  // Ordine dal rango stabile della pagina, NON dal conteggio delle righe qui
  // presenti: con il filtro "aperte" ogni accetta/ignora toglie una riga e un
  // ordine sul conteggio farebbe scavalcare i gruppi sotto il mouse.
  const entries = [...groups.entries()].sort((a, b) => rank(a[0]) - rank(b[0]));

  const labelFor = (key: string) =>
    groupBy === "type" ? t.organize.issues.typeLabel(key) : key;

  const toggle = (key: string) =>
    setCollapsed((cur) => {
      const next = new Set(cur);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });

  const runGroup = async (key: string, fn: () => Promise<void>) => {
    setGroupBusy(key);
    try { await fn(); } finally { setGroupBusy(null); }
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
                      <span className="tnum text-[10px] text-muted">{t.organize.issues.groupMeta(open, list.length)}</span>
                    </button>
                    {open > 0 && (
                      <span className="ml-auto flex gap-1">
                        <button
                          type="button"
                          disabled={groupBusy === key}
                          onClick={() => runGroup(key, () => onAcceptGroup(list))}
                          className="border border-border px-2 py-0.5 text-[10px] text-ok hover:bg-elevated disabled:opacity-40"
                        >{t.organize.issues.groupAccept}</button>
                        <button
                          type="button"
                          disabled={groupBusy === key}
                          onClick={() => runGroup(key, () => onDismissGroup(list))}
                          className="border border-border px-2 py-0.5 text-[10px] text-muted hover:bg-elevated disabled:opacity-40"
                        >{t.organize.issues.groupDismiss}</button>
                      </span>
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
