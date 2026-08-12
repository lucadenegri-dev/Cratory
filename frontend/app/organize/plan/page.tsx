"use client";

import { useCallback, useEffect, useState } from "react";
import { buildPlan, getPlan, type Plan, type PlanStats, type ApplyResult } from "@/lib/organize/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { PlanOps } from "@/components/organize/plan-ops";
import { ApplyModal } from "@/components/organize/apply-modal";
import { Alert, Button, EmptyState, Loading, Spinner } from "@/components/ui";
import { useT } from "@/lib/i18n";

export default function PlanPage() {
  const t = useT();
  const { apply, startApply, refresh } = useJobs();
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [building, setBuilding] = useState(false);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState(false);

  const load = useCallback(() => {
    getPlan()
      .then((p) => { setPlan(p); setOffline(false); })
      .catch((e) => {
        // 404 = nessun draft; un fallimento di rete è offline
        setPlan(null);
        if (e instanceof Error && /fetch|network|raggiung/i.test(e.message)) setOffline(true);
      })
      .finally(() => setLoaded(true));
  }, []);
  useEffect(() => { load(); }, [load]);
  // a fine apply il draft è consumato → pulisci la vista e aggiorna i conteggi
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (apply.status === "done") { setPlan(null); refresh(); }
  }, [apply.status, refresh]);

  const rebuild = async () => {
    setError(null); setBuilding(true);
    try { setPlan(await buildPlan()); setOffline(false); }
    catch (e) { setError(e instanceof Error ? e.message : t.organize.common.error); }
    finally { setBuilding(false); }
  };

  const confirmApply = async () => {
    setModal(false); setError(null);
    try { await startApply(); }
    catch (e) { setError(e instanceof Error ? e.message : t.organize.common.error); }
  };

  const stats = plan?.stats;
  const blocking = stats?.blocking ?? false;
  const nOps = plan?.ops.length ?? 0;
  const applying = apply.status === "running";
  const result = apply.status === "done" ? apply.result : null;

  return (
    <PageLayout
      title="Plan"
      meta={plan ? t.organize.plan.opsCount(nOps) : undefined}
      marginaliaTitle={plan && stats ? t.organize.plan.operations : undefined}
      marginalia={
        plan && stats ? (
          <Marginalia stats={stats} disabled={blocking || nOps === 0 || applying} onApply={() => setModal(true)} />
        ) : undefined
      }
      guide={<>
        <p>{t.organize.plan.guide1}</p>
        <p><b className="text-fg">{t.organize.plan.guide2a}</b>{t.organize.plan.guide2b}<b className="text-fg">{t.organize.plan.guide2c}</b>{t.organize.plan.guide2d}</p>
        <p>{t.organize.plan.guide3}</p>
      </>}
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>{t.organize.common.backendOffline}</Alert>}
        {error && <Alert>{error}</Alert>}
        {apply.status === "error" && <Alert>{t.organize.plan.applyFailed(apply.error ?? t.organize.plan.unknownError)}</Alert>}

        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={rebuild} disabled={building || applying}>
            {building ? <Spinner /> : "↻"} {plan ? t.organize.plan.rebuildLabel : t.organize.plan.buildLabel}{t.organize.plan.buildPlanSuffix}
          </Button>
          {building && <span className="text-xs text-muted">{t.organize.plan.computing}</span>}
        </div>

        {/* Il progresso dell'apply è mostrato dalla barra globale fissa in basso
            (jobs-provider), non più qui: evita il doppio loader. */}

        {result && <ApplyResultBanner result={result} />}

        {plan && plan.conflicts.length > 0 && (
          <div className={`border px-4 py-3 ${blocking ? "border-danger" : "border-border"}`}>
            <div className={`text-xs font-semibold uppercase tracking-wider ${blocking ? "text-danger" : "text-warning"}`}>
              {blocking
                ? t.organize.plan.allConflict
                : t.organize.plan.conflictsCount(plan.conflicts.length)}
            </div>
            <div className="mt-2 flex flex-col gap-1 text-xs text-muted">
              {plan.conflicts.map((c, i) => <div key={i}>· {c.detail}</div>)}
            </div>
            <div className="mt-2 text-[11px] text-faint">{t.organize.plan.conflictHint}</div>
          </div>
        )}

        {!loaded ? <Loading />
          : plan && nOps > 0 ? <PlanOps ops={plan.ops} />
          : plan && nOps === 0 ? <EmptyState title={t.organize.plan.emptyNothingTitle}>{t.organize.plan.emptyNothingBody}</EmptyState>
          : !applying && !result ? <EmptyState title={t.organize.plan.emptyNoPlanTitle}>{t.organize.plan.emptyNoPlanBody}</EmptyState>
          : null}
      </div>

      <ApplyModal open={modal} onClose={() => setModal(false)} stats={stats} onConfirm={confirmApply} />
    </PageLayout>
  );
}

function Marginalia({ stats, disabled, onApply }: { stats: PlanStats; disabled: boolean; onApply: () => void }) {
  const t = useT();
  return (
    <div className="flex flex-col gap-4 text-xs">
      <div className="flex flex-col gap-1.5">
        <Row k={t.organize.plan.rowRetag} v={stats.n_retag} />
        <Row k={t.organize.plan.rowRename} v={stats.n_rename} />
        <Row k={t.organize.plan.rowMove} v={stats.n_move} />
        <Row k={t.organize.plan.rowDelete} v={stats.n_delete} />
        <Row k={t.organize.plan.rowSpaceFreed} v={`${Math.round(stats.space_freed_bytes / (1024 * 1024))} MB`} ok />
        <Row k={t.organize.plan.rowConflicts} v={stats.n_conflicts} danger={stats.n_conflicts > 0} />
        {stats.n_skipped > 0 && <Row k={t.organize.plan.rowSkipped} v={stats.n_skipped} danger />}
      </div>
      <Button variant="danger" onClick={onApply} disabled={disabled} className="w-full">{t.organize.plan.applyButton}</Button>
      <p className="text-[10px] leading-relaxed text-faint">{t.organize.plan.applyHint}</p>
    </div>
  );
}

function Row({ k, v, ok, danger }: { k: string; v: string | number; ok?: boolean; danger?: boolean }) {
  return (
    <div className="flex justify-between">
      <span className="text-muted">{k}</span>
      <span className={`tnum ${danger ? "text-danger" : ok ? "text-ok" : "text-fg-strong"}`}>{v}</span>
    </div>
  );
}

function ApplyResultBanner({ result }: { result: ApplyResult }) {
  const t = useT();
  const ok = !result.refused && !result.partial && !result.error && !result.stale;
  return (
    <div className={`border px-4 py-3 text-xs ${ok ? "border-border" : "border-danger"}`}>
      {result.refused ? (
        <span className="text-danger">{t.organize.plan.resRefused(result.reason ?? "")}</span>
      ) : result.stale ? (
        <span className="text-danger">{t.organize.plan.resStale(result.failed_op_seq)}</span>
      ) : result.partial ? (
        <span className="text-danger">{t.organize.plan.resPartial(result.applied_ops, result.failed_op_seq, result.error ?? "")}</span>
      ) : result.error ? (
        <span className="text-danger">{t.organize.plan.resError(result.error)}</span>
      ) : (
        <span className="text-ok">{t.organize.plan.resSuccess(result.applied_ops, result.skipped_ops, result.run_id)}</span>
      )}
    </div>
  );
}
