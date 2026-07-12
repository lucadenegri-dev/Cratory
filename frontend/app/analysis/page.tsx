"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Gauge } from "lucide-react";
import {
  analysisDivergences, analysisOverview, applyAnalysis, startAnalysis,
  type AnalysisDivergence, type AnalysisOverview,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useJobs } from "@/components/jobs-provider";
import { RekordboxImportCard } from "@/components/analysis/rekordbox-import-card";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EqMeter, Select } from "@/components/ui";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function AnalysisPage() {
  const t = useT();
  const jobs = useJobs();
  const [overview, setOverview] = useState<AnalysisOverview | null>(null);
  const [rows, setRows] = useState<AnalysisDivergence[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [scope, setScope] = useState<"missing" | "all">("missing");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const compatLabel = {
    same: t.analysis.compatSame, compatible: t.analysis.compatCompatible,
    weak: t.analysis.compatWeak, unknown: t.analysis.compatUnknown,
  } as const;

  const reload = useCallback(async () => {
    try {
      const [ov, dv] = await Promise.all([analysisOverview(), analysisDivergences()]);
      setOverview(ov);
      setRows(dv);
      setSelected(new Set());
      setError(null);
    } catch (e) {
      setError(err(e));
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => reload(), 0); // deferred: niente setState sincrono nell'effect
    return () => clearTimeout(timer);
  }, [reload]);

  // Il job di analisi gira in background (barra job globale): quando finisce
  // (running -> done) i dati mostrati qui sono stantii, ricarica in automatico.
  const prevAnalysisStatus = useRef<string | null>(null);
  useEffect(() => {
    const status = jobs.analysis?.status ?? null;
    if (prevAnalysisStatus.current === "running" && status === "done") {
      reload();
    }
    prevAnalysisStatus.current = status;
  }, [jobs.analysis?.status, reload]);

  const onStart = async () => {
    setBusy(true); setError(null); setNotice(null);
    try {
      await startAnalysis(scope);
      jobs.refresh(); // la barra globale aggancia subito il job
      setNotice(t.analysis.startedNote);
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(false);
    }
  };

  const onApply = async (body: Parameters<typeof applyAnalysis>[0]) => {
    setBusy(true); setError(null);
    try {
      const r = await applyAnalysis(body);
      setNotice(t.analysis.appliedSummary(r.applied, r.skipped));
      await reload();
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(false);
    }
  };

  const onForceAll = async () => {
    if (!window.confirm(t.analysis.forceConfirm)) return;
    await onApply({ mode: "all", force: true });
  };

  // Apply selected sovrascrive la provenienza attuale con 'cratory'. Contiamo,
  // fra le righe selezionate, quante calpesterebbero un valore manuale o
  // Rekordbox (per l'avviso) e quante specificamente manuale (per la conferma).
  const selectedRows = rows.filter((r) => selected.has(r.track_id));
  const isProtected = (r: AnalysisDivergence) =>
    r.bpm_source === "manual" || r.bpm_source === "rekordbox" ||
    r.key_source === "manual" || r.key_source === "rekordbox";
  const protectedCount = selectedRows.filter(isProtected).length;
  const manualCount = selectedRows.filter(
    (r) => r.bpm_source === "manual" || r.key_source === "manual").length;

  const onApplySelected = async () => {
    // Le correzioni manuali sono la massima autorità: conferma esplicita prima
    // di sovrascriverle in blocco (il force-all ha già la sua conferma a parte).
    if (manualCount > 0 && !window.confirm(t.analysis.applySelectedConfirm(manualCount))) return;
    await onApply({ track_ids: [...selected] });
  };

  const toggle = (id: number) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });

  // Copertura BPM+key sulle tracce possedute (ready = entrambi presenti),
  // coerente con le tile qui sopra (non il catalogo intero come in dashboard).
  const coveragePct = overview && overview.owned
    ? Math.round((overview.ready_for_set / overview.owned) * 100) : 0;

  const tiles: [string, number][] = overview ? [
    [t.analysis.tileOwned, overview.owned],
    [t.analysis.tileReady, overview.ready_for_set],
    [t.analysis.tileMissingBpm, overview.missing_bpm],
    [t.analysis.tileMissingKey, overview.missing_key],
    [t.analysis.tileAnalyzed, overview.analyzed],
    [t.analysis.tileDivergent, overview.divergent],
  ] : [];

  return (
    <PageLayout title={t.analysis.pageTitle}>
      <div className="space-y-6">
        <p className="text-sm text-muted">{t.analysis.intro}</p>

        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {notice && <Alert tone="success">{notice}</Alert>}

        {overview && (
          <Card>
            <div className="grid grid-cols-2 divide-x divide-y divide-border sm:grid-cols-3 lg:grid-cols-6 lg:divide-y-0">
              {tiles.map(([label, value]) => (
                <div key={label} className="px-4 py-3">
                  <p className="text-[10px] uppercase tracking-wider text-muted">{label}</p>
                  <p className="tnum text-lg font-semibold text-fg-strong">{value}</p>
                </div>
              ))}
            </div>
            <p className="border-t border-border px-4 py-2 text-[11px] text-faint">
              {t.analysis.bySourceBpm(overview.bpm_by_source.manual ?? 0,
                overview.bpm_by_source.rekordbox ?? 0, overview.bpm_by_source.cratory ?? 0)}
              {" · "}
              {t.analysis.bySourceKey(overview.key_by_source.manual ?? 0,
                overview.key_by_source.rekordbox ?? 0, overview.key_by_source.cratory ?? 0)}
            </p>
          </Card>
        )}

        {overview && (
          <Card>
            <div className="px-4 py-3">
              <div className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted">
                <Gauge size={12} className="text-faint" /> {t.dashboard.bpmKeyCoverage}
              </div>
              <div className="mb-1 flex justify-between text-xs">
                <span className="text-muted">{t.dashboard.bpmKeyLabel}</span>
                <span className="tnum text-muted">
                  {overview.ready_for_set}/{overview.owned} · {coveragePct}%
                </span>
              </div>
              <EqMeter value={coveragePct} calm className="h-4 w-full" />
            </div>
          </Card>
        )}

        <Card>
          <h2 className="px-4 pt-3 text-xs font-semibold uppercase tracking-wider text-muted">
            {t.analysis.rekordboxHeading}
          </h2>
          <RekordboxImportCard pending={overview?.rekordbox_pending ?? 0} onImported={reload} />
        </Card>

        <Card>
          <h2 className="px-4 pt-3 text-xs font-semibold uppercase tracking-wider text-muted">
            {t.analysis.analysisHeading}
          </h2>
          <div className="flex flex-wrap items-end gap-3 px-4 py-3 text-xs">
            <label className="block">
              <span className="mb-1 block text-[10px] uppercase tracking-wider text-muted">
                {t.analysis.scopeLabel}
              </span>
              <Select
                className="h-9 w-56"
                value={scope}
                onChange={(e) => setScope(e.target.value as "missing" | "all")}
              >
                <option value="missing">{t.analysis.scopeMissing}</option>
                <option value="all">{t.analysis.scopeAll}</option>
              </Select>
            </label>
            <Button size="sm" onClick={onStart} disabled={busy}>
              {t.analysis.startButton}
            </Button>
          </div>
        </Card>

        <Card>
          <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
            <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">
              {t.analysis.divergencesHeading}
            </h2>
            <div className="flex flex-col items-end gap-1">
              <div className="flex gap-2">
                <Button
                  size="sm" variant="outline"
                  disabled={busy || selected.size === 0}
                  onClick={onApplySelected}
                >
                  {t.analysis.applySelected(selected.size)}
                </Button>
                <Button
                  size="sm" variant="danger"
                  disabled={busy || (overview?.analyzed ?? 0) === 0}
                  onClick={onForceAll}
                >
                  {t.analysis.forceApplyAll}
                </Button>
              </div>
              {protectedCount > 0 && (
                <Badge tone="warning">{t.analysis.applySelectedProtected(protectedCount)}</Badge>
              )}
            </div>
          </div>
          {rows.length === 0 ? (
            <p className="border-t border-border px-4 py-4 text-xs text-muted">
              {t.analysis.divergencesEmpty}
            </p>
          ) : (
            <div className="overflow-x-auto border-t border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-muted">
                    <th className="px-4 py-2" />
                    <th className="px-2 py-2">{t.analysis.colTrack}</th>
                    <th className="px-2 py-2">{t.analysis.colCurrent}</th>
                    <th className="px-2 py-2">{t.analysis.colAnalysis}</th>
                    <th className="px-2 py-2 text-right">{t.analysis.colDelta}</th>
                    <th className="px-2 py-2">{t.analysis.colKeyCompat}</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.track_id} className="border-t border-border">
                      <td className="px-4 py-2">
                        <input
                          type="checkbox"
                          checked={selected.has(r.track_id)}
                          onChange={() => toggle(r.track_id)}
                          className="accent-fg-strong"
                          aria-label={`${r.artist ?? "?"} — ${r.title ?? "?"}`}
                        />
                      </td>
                      <td className="max-w-[16rem] truncate px-2 py-2 text-fg">
                        {r.artist ?? "?"} — {r.title ?? "?"}
                      </td>
                      <td className="tnum px-2 py-2 text-muted">
                        {r.bpm ?? "—"} · {r.camelot_key ?? "—"}
                        {(r.bpm_source ?? r.key_source) && (
                          <span className="ml-1 text-[10px] text-faint">
                            ({r.bpm_source ?? r.key_source})
                          </span>
                        )}
                      </td>
                      <td className="tnum px-2 py-2 text-fg">
                        {r.analysis_bpm ?? "—"} · {r.analysis_camelot ?? "—"}
                      </td>
                      <td className="tnum px-2 py-2 text-right">
                        {r.bpm_delta != null ? (r.bpm_delta > 0 ? `+${r.bpm_delta}` : r.bpm_delta) : "—"}
                      </td>
                      <td className="px-2 py-2">
                        <Badge tone={r.key_compatibility === "weak" ? "danger" : "neutral"}>
                          {compatLabel[r.key_compatibility]}
                        </Badge>
                      </td>
                      <td className="px-4 py-2 text-right">
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => onApply({ track_ids: [r.track_id] })}
                          className="text-[11px] uppercase tracking-wider text-fg-strong hover:underline disabled:opacity-50"
                        >
                          {t.analysis.applyRow}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </PageLayout>
  );
}
