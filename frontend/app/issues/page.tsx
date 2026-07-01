"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  listIssues, listSources, setIssueStatus, fixIssue, bulkIssues, aiSuggestTags, aiSuggestGenres,
  bridgeSuggest, type Issue, type ScanRoot,
} from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { IssuesTable } from "@/components/issues-table";
import { Alert, Button, EmptyState, Select } from "@/components/ui";

export default function IssuesPage() {
  const { scan } = useJobs();
  const [issues, setIssues] = useState<Issue[]>([]);
  const [roots, setRoots] = useState<ScanRoot[]>([]);
  const [offline, setOffline] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [genreBusy, setGenreBusy] = useState(false);
  const [bridgeBusy, setBridgeBusy] = useState(false);
  const [aiNote, setAiNote] = useState<string | null>(null);

  const [sev, setSev] = useState("");
  const [type, setType] = useState("");
  const [field, setField] = useState("");
  const [status, setStatus] = useState("open");
  const [rootId, setRootId] = useState("");

  const load = useCallback(() => {
    listIssues()
      .then((r) => { setIssues(r); setOffline(false); })
      .catch(() => setOffline(true));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { listSources().then(setRoots).catch(() => {}); }, []);
  useEffect(() => { if (scan.status === "done") load(); }, [scan.status, load]);

  const act = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try { await fn(); load(); }
    catch (e) { setActionError(e instanceof Error ? e.message : "Errore"); }
  };
  const onFix = (id: number, value: string) => act(() => fixIssue(id, value));
  const onDismiss = (id: number) => act(() => setIssueStatus(id, "dismissed"));
  const onReopen = (id: number) => act(() => setIssueStatus(id, "open"));
  const acceptAllFixable = () => act(() => bulkIssues({ status: "accepted" }));
  const dismissAllInfo = () => act(() => bulkIssues({ severity: "info", status: "dismissed" }));

  const onAiSuggest = async () => {
    setActionError(null);
    setAiNote(null);
    setAiBusy(true);
    try {
      const r = await aiSuggestTags();
      if (!r.configured) {
        setActionError("Imposta ANTHROPIC_API_KEY nel backend per usare l'AI.");
      } else {
        load();
        setAiNote(
          `${r.suggested} suggerimenti pronti${r.unresolved > 0 ? `, ${r.unresolved} non ricavabili dal nome file` : ""} — rivedi e accetta col ✓.`,
        );
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Errore");
    } finally {
      setAiBusy(false);
    }
  };

  const onAiGenres = async () => {
    setActionError(null);
    setAiNote(null);
    setGenreBusy(true);
    try {
      const r = await aiSuggestGenres();
      if (!r.configured) {
        setActionError("Imposta ANTHROPIC_API_KEY nel backend per usare l'AI.");
      } else {
        load();
        setAiNote(
          `${r.suggested} generi suggeriti — mancanti + sporchi (bassa confidenza, rivedi)${r.unresolved > 0 ? `, ${r.unresolved} non ricavabili` : ""} — accetta col ✓.`,
        );
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Errore");
    } finally {
      setGenreBusy(false);
    }
  };

  const onBridge = async () => {
    setActionError(null);
    setAiNote(null);
    setBridgeBusy(true);
    try {
      const r = await bridgeSuggest();
      if (!r.configured) {
        setActionError("Configura l'URL di Cratory in Settings (e verifica che Cratory sia in esecuzione).");
      } else {
        load();
        setAiNote(
          `${r.suggested} suggerimenti da Cratory${r.mismatches > 0 ? `, ${r.mismatches} discrepanze ISRC segnalate` : ""}${r.unresolved > 0 ? `, ${r.unresolved} non trovati` : ""} — rivedi e accetta col ✓.`,
        );
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Errore");
    } finally {
      setBridgeBusy(false);
    }
  };

  const types = useMemo(() => [...new Set(issues.map((i) => i.type))].sort(), [issues]);
  const fields = useMemo(
    () => [...new Set(issues.map((i) => i.field).filter((f): f is string => !!f))].sort(),
    [issues],
  );

  const filtered = issues.filter((i) =>
    (!sev || i.severity === sev) &&
    (!type || i.type === type) &&
    (!field || i.field === field) &&
    (!status || i.status === status) &&
    (!rootId || i.root_id === Number(rootId)),
  );

  const bySev: Record<string, number> = { error: 0, warning: 0, info: 0 };
  const byType: Record<string, number> = {};
  let accepted = 0;
  for (const i of issues) {
    bySev[i.severity] = (bySev[i.severity] ?? 0) + 1;
    byType[i.type] = (byType[i.type] ?? 0) + 1;
    if (i.status === "accepted") accepted++;
  }

  return (
    <PageLayout
      title="Issues"
      meta={`${filtered.length} / ${issues.length}`}
      marginaliaTitle="Riepilogo"
      marginalia={
        <Marginalia
          total={issues.length} bySev={bySev} byType={byType} accepted={accepted}
          onAcceptFixable={acceptAllFixable} onDismissInfo={dismissAllInfo}
          onAiSuggest={onAiSuggest} aiBusy={aiBusy}
          onAiGenres={onAiGenres} genreBusy={genreBusy}
          onBridge={onBridge} bridgeBusy={bridgeBusy}
        />
      }
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}
        {actionError && <Alert>{actionError}</Alert>}
        {aiNote && <Alert tone="info">{aiNote}</Alert>}

        <div className="flex flex-wrap gap-2">
          <Select value={sev} onChange={(e) => setSev(e.target.value)} className="w-auto">
            <option value="">severità: tutte</option>
            <option value="error">error</option>
            <option value="warning">warning</option>
            <option value="info">info</option>
          </Select>
          <Select value={type} onChange={(e) => setType(e.target.value)} className="w-auto">
            <option value="">tipo: tutti</option>
            {types.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
          <Select value={field} onChange={(e) => setField(e.target.value)} className="w-auto">
            <option value="">campo: tutti</option>
            {fields.map((f) => <option key={f} value={f}>{f}</option>)}
          </Select>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-auto">
            <option value="open">aperte</option>
            <option value="accepted">accettate</option>
            <option value="dismissed">ignorate</option>
            <option value="">tutti gli stati</option>
          </Select>
          <Select value={rootId} onChange={(e) => setRootId(e.target.value)} className="w-auto">
            <option value="">tutte le radici</option>
            {roots.map((r) => <option key={r.id} value={r.id}>{r.label || r.path}</option>)}
          </Select>
        </div>

        {filtered.length === 0 && !offline ? (
          <EmptyState title="Nessuna issue">
            {issues.length === 0 ? "La libreria è pulita (o non ancora scansionata)." : "Nessuna issue con questi filtri."}
          </EmptyState>
        ) : (
          <IssuesTable issues={filtered} onFix={onFix} onDismiss={onDismiss} onReopen={onReopen} />
        )}
      </div>
    </PageLayout>
  );
}

function Marginalia({ total, bySev, byType, accepted, onAcceptFixable, onDismissInfo, onAiSuggest, aiBusy, onAiGenres, genreBusy, onBridge, bridgeBusy }: {
  total: number;
  bySev: Record<string, number>;
  byType: Record<string, number>;
  accepted: number;
  onAcceptFixable: () => void;
  onDismissInfo: () => void;
  onAiSuggest: () => void;
  aiBusy: boolean;
  onAiGenres: () => void;
  genreBusy: boolean;
  onBridge: () => void;
  bridgeBusy: boolean;
}) {
  return (
    <div className="flex flex-col gap-4 text-xs">
      <div>
        <div className="tnum text-2xl leading-none text-fg-strong">{total}</div>
        <div className="mt-1 text-[10px] uppercase tracking-wider text-muted">issue</div>
        <div className="mt-1 flex gap-3 text-[11px]">
          <span className="text-danger">{bySev.error ?? 0} err</span>
          <span className="text-warning">{bySev.warning ?? 0} warn</span>
          <span className="text-muted">{bySev.info ?? 0} info</span>
        </div>
      </div>
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">per tipo</div>
        <div className="flex flex-col gap-1">
          {Object.entries(byType).sort((a, b) => b[1] - a[1]).map(([t, n]) => (
            <div key={t} className="flex justify-between"><span className="text-muted">{t}</span><span className="tnum text-fg">{n}</span></div>
          ))}
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-wider text-muted">accettate</div>
        <div className="mt-1 text-[11px] text-ok">{accepted} → andranno nel PLAN</div>
      </div>
      <div className="flex flex-col gap-2">
        <Button variant="primary" size="sm" onClick={onAiSuggest} disabled={aiBusy}>
          {aiBusy ? "AI in corso…" : "✨ Suggerisci artista/titolo"}
        </Button>
        <Button variant="primary" size="sm" onClick={onAiGenres} disabled={genreBusy}>
          {genreBusy ? "AI in corso…" : "✨ Suggerisci genere"}
        </Button>
        <Button variant="primary" size="sm" onClick={onBridge} disabled={bridgeBusy}>
          {bridgeBusy ? "Cratory in corso…" : "⇄ Suggerisci da Cratory"}
        </Button>
        <Button variant="outline" size="sm" onClick={onAcceptFixable}>✓ accetta tutti i fixabili</Button>
        <Button variant="outline" size="sm" onClick={onDismissInfo}>✕ ignora tutti gli info</Button>
      </div>
    </div>
  );
}
