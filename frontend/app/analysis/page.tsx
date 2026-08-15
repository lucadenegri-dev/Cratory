"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  analysisDivergences, analysisOverview, applyAnalysis, dismissAnalysis, errText, startAnalysis,
  type AnalysisDivergence, type AnalysisOverview,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { useJobs } from "@/components/jobs-provider";
import { RekordboxImportCard } from "@/components/analysis/rekordbox-import-card";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, CardHeader, Field, Select } from "@/components/ui";
import { ButtonLink } from "@/components/button-link";
import { ConfirmModal } from "@/components/confirm-modal";

type ConfirmAction = "force" | "selected" | "divergent";
type SourceKey = "manual" | "rekordbox" | "cratory";

/** Le tracce non pronte sono quelle possedute senza BPM o senza key: in Library
 *  è esattamente status=imported + owned=true (ready_for_set = BPM+key presenti). */
const NOT_READY_HREF = "/library?status=imported&owned=true";

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
  const [confirmAction, setConfirmAction] = useState<ConfirmAction | null>(null);

  const compatLabel = {
    same: t.analysis.compatSame, compatible: t.analysis.compatCompatible,
    weak: t.analysis.compatWeak, unknown: t.analysis.compatUnknown,
  } as const;

  const sourceLabel = (s: string | null | undefined) => {
    const map: Record<SourceKey, string> = {
      manual: t.analysis.sourceManual,
      rekordbox: t.analysis.sourceRekordbox,
      cratory: t.analysis.sourceCratory,
    };
    return s && s in map ? map[s as SourceKey] : null;
  };

  const reload = useCallback(async () => {
    try {
      const [ov, dv] = await Promise.all([analysisOverview(), analysisDivergences()]);
      setOverview(ov);
      setRows(dv);
      setSelected(new Set());
      setError(null);
    } catch (e) {
      setError(errText(e));
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
      // Essentia assente: il backend risponde 503 analysis_engine_unavailable.
      const msg = errText(e);
      setError(msg.includes("analysis_engine_unavailable") ? t.analysis.engineUnavailable : msg);
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
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  // «Ignora» non sovrascrive nulla (il canonico resta): niente conferma.
  const onDismiss = async (ids: number[]) => {
    setBusy(true); setError(null);
    try {
      const r = await dismissAnalysis(ids);
      setNotice(t.analysis.ignoredSummary(r.dismissed));
      await reload();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  // Applicare sovrascrive la provenienza attuale con 'cratory'. Contiamo quante
  // righe calpesterebbero un valore manuale o Rekordbox (per l'avviso) e quante
  // specificamente manuale (per la conferma: il manuale è la massima autorità).
  const isProtected = (r: AnalysisDivergence) =>
    r.bpm_source === "manual" || r.bpm_source === "rekordbox" ||
    r.key_source === "manual" || r.key_source === "rekordbox";
  const isManual = (r: AnalysisDivergence) =>
    r.bpm_source === "manual" || r.key_source === "manual";

  const selectedRows = useMemo(() => rows.filter((r) => selected.has(r.track_id)), [rows, selected]);
  const protectedCount = selectedRows.filter(isProtected).length;
  const manualCount = selectedRows.filter(isManual).length;
  // mode='divergent' è "scelta esplicita" lato backend: nessuna guardia sui
  // manuali là, quindi la conferma la impone il frontend come per le selezionate.
  const divergentManualCount = rows.filter(isManual).length;

  const onApplySelected = async () => {
    if (manualCount > 0) { setConfirmAction("selected"); return; }
    await onApply({ track_ids: [...selected] });
  };

  const onApplyAllDivergent = async () => {
    if (divergentManualCount > 0) { setConfirmAction("divergent"); return; }
    await onApply({ mode: "divergent" });
  };

  const onConfirmAction = async () => {
    const action = confirmAction;
    setConfirmAction(null);
    if (action === "force") await onApply({ mode: "all", force: true });
    else if (action === "selected") await onApply({ track_ids: [...selected] });
    else if (action === "divergent") await onApply({ mode: "divergent" });
  };

  const toggle = (id: number) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });

  const allSelected = rows.length > 0 && selected.size === rows.length;
  const toggleAll = () =>
    setSelected(allSelected ? new Set() : new Set(rows.map((r) => r.track_id)));

  // Copertura sulle possedute. Math.floor + cap a 99: arrotondare per eccesso
  // farebbe dire "100%" con una traccia ancora non pronta (411/412 = 99,75).
  const notReady = overview ? overview.owned - overview.ready_for_set : 0;

  // Tracce a cui manca UN campo su due. scope='missing' seleziona le TRACCE cui
  // manca almeno un campo, e il job scrive sempre entrambi gli analysis_*: solo
  // su queste il campo già presente può essere contraddetto (-> divergenza).
  // Inclusione-esclusione sui conteggi che l'overview già espone:
  //   pending = |manca bpm ∪ manca key| = missing_bpm + missing_key - |entrambi|
  //   => esattamente uno = pending - |entrambi| = 2*pending - missing_bpm - missing_key
  const missingHalf = overview
    ? Math.max(0, 2 * overview.rekordbox_pending - overview.missing_bpm - overview.missing_key)
    : 0;
  const coveragePct = overview && overview.owned
    ? (notReady === 0 ? 100 : Math.min(99, Math.floor((overview.ready_for_set / overview.owned) * 100)))
    : 0;

  const marginalia = overview ? (
    // La copertura sta già accanto al titolo (meta): ripeterla qui sarebbe la
    // stessa duplicazione del vecchio meter che restava a ridire il numero.
    <dl className="space-y-3 text-xs">
      <Stat label={t.analysis.statOwned} value={overview.owned} />
      <Stat label={t.analysis.statReady} value={overview.ready_for_set} />
      <Stat label={t.analysis.statNotReady} value={notReady} strong={notReady > 0} />
      {/* analyzed = passate per Essentia; cratory = dove Essentia ha vinto. Due
          fatti diversi: senza le note sembrano un conteggio che si contraddice. */}
      <Stat label={t.analysis.statAnalyzed} value={overview.analyzed} hint={t.analysis.statAnalyzedHint} />
      <div className="border-t border-border pt-3">
        <dt className="mb-1 text-[10px] uppercase tracking-wider text-muted">{t.analysis.bySourceBpmTitle}</dt>
        <dd className="tnum text-muted">
          {t.analysis.bySourceRow(overview.bpm_by_source.manual ?? 0,
            overview.bpm_by_source.rekordbox ?? 0, overview.bpm_by_source.cratory ?? 0)}
        </dd>
      </div>
      <div>
        <dt className="mb-1 text-[10px] uppercase tracking-wider text-muted">{t.analysis.bySourceKeyTitle}</dt>
        <dd className="tnum text-muted">
          {t.analysis.bySourceRow(overview.key_by_source.manual ?? 0,
            overview.key_by_source.rekordbox ?? 0, overview.key_by_source.cratory ?? 0)}
        </dd>
      </div>
    </dl>
  ) : null;

  return (
    <PageLayout
      title={t.analysis.pageTitle}
      meta={overview ? t.analysis.coverageMeta(overview.ready_for_set, overview.owned, coveragePct) : undefined}
      marginaliaTitle={t.analysis.statsTitle}
      marginalia={marginalia}
    >
      <div className="space-y-5">
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {notice && <Alert tone="success">{notice}</Alert>}

        {/* Lede: la risposta a "cosa faccio adesso?", non un referto di sei numeri. */}
        {overview && (
          notReady > 0 ? (
            // Il bottone sta sotto la spiegazione, non accanto: con l'hint su
            // una riga intera un flex-wrap lo farebbe migrare a seconda della
            // larghezza della finestra. Qui l'ordine è sempre lo stesso.
            <div>
              <p className="text-sm font-semibold text-fg-strong">{t.analysis.ledeNotReady(notReady)}</p>
              <p className="mt-0.5 max-w-[75ch] text-xs text-muted">{t.analysis.ledeHint}</p>
              <ButtonLink href={NOT_READY_HREF} variant="outline" size="sm" className="mt-3">
                {notReady === 1 ? t.analysis.ledeNotReadyCta : t.analysis.ledeNotReadyCtaPlural}
              </ButtonLink>
            </div>
          ) : (
            <p className="text-sm text-muted">{t.analysis.ledeAllReady(overview.owned)}</p>
          )
        )}

        {/* Sorgenti: una card sola, con la precedenza dichiarata. Rekordbox è la
            primaria (regola 2 di CLAUDE.md), l'analisi in-app è l'alternativa
            sotto un filetto — non una card di pari rango. */}
        <Card>
          <CardHeader
            title={t.analysis.sourcesHeading}
            subtitle={t.analysis.sourcesSubtitle}
          />

          {/* La gerarchia su una riga sua: è la regola che governa tutta la card,
              non una nota a margine della testata. */}
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-border bg-surface-2 px-5 py-2.5">
            <span className="text-[10px] uppercase tracking-wider text-muted">{t.analysis.precedenceLabel}</span>
            <span className="whitespace-nowrap text-xs font-semibold text-fg-strong">{t.analysis.precedenceValue}</span>
          </div>

          <RekordboxImportCard onImported={reload} />

          <section className="border-t border-border px-5 py-4">
            {/* Nessun badge qui: il rango lo dicono già l'ordine, la striscia
                della precedenza e il "PRIMARY" sopra. Un badge "ALTERNATIVE"
                sarebbe rumore — e il badge neutro non passa AA (4.28:1). */}
            <h4 className="mb-2 text-sm font-semibold uppercase tracking-wider text-fg-strong">
              {t.analysis.analysisHeading}
            </h4>
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-72">
                <Field label={t.analysis.scopeLabel}>
                  <Select
                    className="h-9 w-full"
                    value={scope}
                    onChange={(e) => setScope(e.target.value as "missing" | "all")}
                  >
                    <option value="missing">{t.analysis.scopeMissing}</option>
                    <option value="all">{t.analysis.scopeAll}</option>
                  </Select>
                </Field>
              </div>
              <Button size="sm" onClick={onStart} disabled={busy}>
                {t.analysis.startButton}
              </Button>
            </div>
            {/* L'hint dice PRIMA del click cosa farà davvero l'analisi, e segue
                lo scope: le due voci non hanno lo stesso raggio d'azione.
                Sotto i controlli e non dentro il Field, così non sfalsa
                l'allineamento del bottone. */}
            <p className="mt-2 max-w-[68ch] text-xs text-muted">
              {scope === "missing" ? (
                <>
                  {t.analysis.scopeHintMissing(notReady)}
                  {missingHalf > 0 && t.analysis.scopeHintMissingHalf(missingHalf)}
                </>
              ) : (
                t.analysis.scopeHintAll(overview?.owned ?? 0)
              )}
            </p>
          </section>
        </Card>

        {/* Divergenze: a zero è una riga, non un'intestazione con un bottone
            rosso armato. Si arma solo quando c'è davvero da riconciliare. */}
        {rows.length === 0 ? (
          <p className="text-xs text-muted">{t.analysis.divergencesEmpty}</p>
        ) : (
          <Card>
            <CardHeader
              title={t.analysis.divergencesHeading}
              subtitle={t.analysis.divergencesCount(rows.length)}
              action={
                <div className="flex flex-col items-end gap-1.5">
                  <div className="flex flex-wrap justify-end gap-2">
                    <Button
                      size="sm" variant="outline"
                      disabled={busy || selected.size === 0}
                      onClick={() => onDismiss([...selected])}
                    >
                      {t.analysis.ignoreSelected(selected.size)}
                    </Button>
                    <Button
                      size="sm" variant="outline"
                      disabled={busy || selected.size === 0}
                      onClick={onApplySelected}
                    >
                      {t.analysis.applySelected(selected.size)}
                    </Button>
                    <Button size="sm" disabled={busy} onClick={onApplyAllDivergent}>
                      {t.analysis.applyAllDivergent(rows.length)}
                    </Button>
                  </div>
                  {protectedCount > 0 && (
                    // L'avviso stava a 10px muted accanto al bottone più forte:
                    // il testo più silenzioso della pagina davanti al rischio
                    // più alto. Promosso a fg-strong, senza introdurre colore.
                    <p className="text-right text-xs font-semibold text-fg-strong">
                      {t.analysis.applySelectedProtected(protectedCount)}
                    </p>
                  )}
                </div>
              }
            />
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-muted">
                    <th className="px-4 py-2">
                      <input
                        type="checkbox"
                        checked={allSelected}
                        onChange={toggleAll}
                        className="h-4 w-4 accent-[var(--color-fg)]"
                        aria-label={t.analysis.selectAll}
                      />
                    </th>
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
                          className="h-4 w-4 accent-[var(--color-fg)]"
                          aria-label={`${r.artist ?? "?"} — ${r.title ?? "?"}`}
                        />
                      </td>
                      <td className="max-w-[16rem] truncate px-2 py-2 text-fg">
                        {r.artist ?? "?"} — {r.title ?? "?"}
                      </td>
                      {/* Provenienza per valore: una sola etichetta per due valori
                          nascondeva una correzione manuale quando le fonti differiscono. */}
                      <td className="tnum px-2 py-2 text-muted">
                        <Provenance value={r.bpm} source={r.bpm_source} label={sourceLabel(r.bpm_source)} />
                        {" · "}
                        <Provenance value={r.camelot_key} source={r.key_source} label={sourceLabel(r.key_source)} />
                      </td>
                      <td className="tnum px-2 py-2 text-fg">
                        {r.analysis_bpm ?? "—"} · {r.analysis_camelot ?? "—"}
                      </td>
                      <td className="tnum px-2 py-2 text-right">
                        {r.bpm_delta != null ? (r.bpm_delta > 0 ? `+${r.bpm_delta}` : r.bpm_delta) : "—"}
                      </td>
                      <td className="px-2 py-2">
                        {/* Una key divergente è un conflitto, non un errore: sotto
                            la One-Red Rule resta monocroma (era tone="danger"). */}
                        <Badge tone={r.key_compatibility === "weak" ? "primary" : "neutral"}>
                          {compatLabel[r.key_compatibility]}
                        </Badge>
                      </td>
                      <td className="px-4 py-2 text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            size="sm" variant="ghost"
                            disabled={busy}
                            onClick={() => onDismiss([r.track_id])}
                          >
                            {t.analysis.ignoreRow}
                          </Button>
                          <Button
                            size="sm" variant="ghost"
                            disabled={busy}
                            onClick={() => onApply({ track_ids: [r.track_id] })}
                          >
                            {t.analysis.applyRow}
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Force: gate su divergent > 0 (prima era su analyzed, quindi armato
                a vuoto) e demoto da bottone rosso in testata a link nel corpo. */}
            <div className="border-t border-border px-5 py-3 text-right">
              <button
                type="button"
                disabled={busy}
                onClick={() => setConfirmAction("force")}
                className="text-[11px] uppercase tracking-wider text-muted underline-offset-2 transition-colors hover:text-danger focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-fg disabled:opacity-50"
              >
                {t.analysis.forceApplyAll}
              </button>
            </div>
          </Card>
        )}
      </div>

      <ConfirmModal
        open={confirmAction !== null}
        message={
          confirmAction === "selected" ? t.analysis.applySelectedConfirm(manualCount)
            : confirmAction === "divergent" ? t.analysis.applySelectedConfirm(divergentManualCount)
              : t.analysis.forceConfirm
        }
        tone="danger"
        onConfirm={onConfirmAction}
        onClose={() => setConfirmAction(null)}
      />
    </PageLayout>
  );
}

/** Riga label/valore della marginalia. */
function Stat({ label, value, hint, strong }: {
  label: string; value: string | number; hint?: string; strong?: boolean;
}) {
  return (
    <div>
      <dt className="text-[10px] uppercase tracking-wider text-muted">{label}</dt>
      <dd className={strong ? "tnum text-sm font-semibold text-fg-strong" : "tnum text-sm text-fg"}>{value}</dd>
      {hint && <p className="text-[10px] text-muted">{hint}</p>}
    </div>
  );
}

/** Valore + fonte. Il manuale è la massima autorità: si legge a colpo d'occhio. */
function Provenance({ value, source, label }: {
  value: number | string | null; source: string | null | undefined; label: string | null;
}) {
  const manual = source === "manual";
  return (
    <span className={manual ? "text-fg-strong" : undefined}>
      {value ?? "—"}
      {label && <span className="ml-1 text-[10px] text-muted">({label})</span>}
    </span>
  );
}
