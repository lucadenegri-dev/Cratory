"use client";

import { useCallback, useEffect, useState } from "react";
import { buildPlan, getPlan, type Plan, type PlanStats, type ApplyResult } from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { PlanOps } from "@/components/plan-ops";
import { ApplyModal } from "@/components/apply-modal";
import { Alert, Button, EmptyState, EqMeter } from "@/components/ui";

export default function PlanPage() {
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
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
    finally { setBuilding(false); }
  };

  const confirmApply = async () => {
    setModal(false); setError(null);
    try { await startApply(); }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
  };

  const stats = plan?.stats;
  const blocking = stats?.blocking ?? false;
  const nOps = plan?.ops.length ?? 0;
  const applying = apply.status === "running";
  const result = apply.status === "done" ? apply.result : null;

  return (
    <PageLayout
      title="Plan"
      meta={plan ? `${nOps} operazioni` : undefined}
      marginaliaTitle={plan && stats ? "Operazioni" : undefined}
      marginalia={
        plan && stats ? (
          <Marginalia stats={stats} disabled={blocking || nOps === 0 || applying} onApply={() => setModal(true)} />
        ) : undefined
      }
      guide={<>
        <p>Anteprima delle operazioni dalle issue accettate: retag, sposta, rinomina, elimina.</p>
        <p><b className="text-fg">Applica</b> scrive davvero sul disco: i tag <b className="text-fg">dentro i file audio</b> e gli spostamenti/rinomine. Prima di allora nulla cambia.</p>
        <p>Reversibile: i delete vanno in quarantena e ogni run ha un undo.</p>
      </>}
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}
        {error && <Alert>{error}</Alert>}
        {apply.status === "error" && <Alert>Apply fallito: {apply.error ?? "errore sconosciuto"}</Alert>}

        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={rebuild} disabled={building || applying}>
            ↻ {plan ? "ricostruisci" : "costruisci"} il piano
          </Button>
          {building && <span className="text-xs text-muted">calcolo…</span>}
        </div>

        {applying && (
          <div className="flex flex-col gap-2 border border-border bg-surface px-4 py-3">
            <div className="flex items-center justify-between">
              <span className="text-xs uppercase tracking-wider text-fg-strong">Applicazione in corso{apply.phase ? ` · ${apply.phase}` : ""}</span>
              <span className="tnum text-xs text-fg-strong">{apply.processed} / {apply.total || "?"}</span>
            </div>
            <EqMeter value={apply.total > 0 ? Math.round((apply.processed / apply.total) * 100) : null} className="h-6 w-full" />
          </div>
        )}

        {result && <ApplyResultBanner result={result} />}

        {plan && plan.conflicts.length > 0 && (
          <div className={`border px-4 py-3 ${blocking ? "border-danger" : "border-border"}`}>
            <div className={`text-xs font-semibold uppercase tracking-wider ${blocking ? "text-danger" : "text-warning"}`}>
              {blocking
                ? "Niente da applicare: tutte le operazioni sono in conflitto"
                : `${plan.conflicts.length} conflitti — le operazioni coinvolte verranno saltate`}
            </div>
            <div className="mt-2 flex flex-col gap-1 text-xs text-muted">
              {plan.conflicts.map((c, i) => <div key={i}>· {c.detail}</div>)}
            </div>
            <div className="mt-2 text-[11px] text-faint">Il resto del piano si applica comunque. Risolvi in ISSUES / DUPLICATES / SETTINGS e ricostruisci per recuperare gli op saltati.</div>
          </div>
        )}

        {!loaded ? null
          : plan && nOps > 0 ? <PlanOps ops={plan.ops} />
          : plan && nOps === 0 ? <EmptyState title="Niente da applicare">Accetta delle issue o scegli i doppioni, poi ricostruisci.</EmptyState>
          : !applying && !result ? <EmptyState title="Nessun piano">Costruisci il piano dalle tue decisioni in ISSUES e DUPLICATES.</EmptyState>
          : null}
      </div>

      <ApplyModal open={modal} onClose={() => setModal(false)} stats={stats} onConfirm={confirmApply} />
    </PageLayout>
  );
}

function Marginalia({ stats, disabled, onApply }: { stats: PlanStats; disabled: boolean; onApply: () => void }) {
  return (
    <div className="flex flex-col gap-4 text-xs">
      <div className="flex flex-col gap-1.5">
        <Row k="retag" v={stats.n_retag} />
        <Row k="rinomina" v={stats.n_rename} />
        <Row k="sposta" v={stats.n_move} />
        <Row k="elimina" v={stats.n_delete} />
        <Row k="spazio liberato" v={`${Math.round(stats.space_freed_bytes / (1024 * 1024))} MB`} ok />
        <Row k="conflitti" v={stats.n_conflicts} danger={stats.n_conflicts > 0} />
        {stats.n_skipped > 0 && <Row k="saltate" v={stats.n_skipped} danger />}
      </div>
      <Button variant="danger" onClick={onApply} disabled={disabled} className="w-full">▶ Applica il piano</Button>
      <p className="text-[10px] leading-relaxed text-faint">Apre un riepilogo di conferma. Tutto annullabile da HISTORY; gli eliminati vanno in quarantena.</p>
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
  const ok = !result.refused && !result.partial && !result.error && !result.stale;
  return (
    <div className={`border px-4 py-3 text-xs ${ok ? "border-border" : "border-danger"}`}>
      {result.refused ? (
        <span className="text-danger">Apply rifiutato{result.reason ? `: ${result.reason}` : ""}.</span>
      ) : result.stale ? (
        <span className="text-danger">Piano non più valido (op #{result.failed_op_seq}). Ricostruisci il piano.</span>
      ) : result.partial ? (
        <span className="text-danger">Applicate {result.applied_ops} operazioni, fermato all&apos;op #{result.failed_op_seq}{result.error ? `: ${result.error}` : ""}.</span>
      ) : result.error ? (
        <span className="text-danger">Errore: {result.error}</span>
      ) : (
        <span className="text-ok">
          ✓ Applicate {result.applied_ops} operazioni
          {result.skipped_ops > 0 ? ` (${result.skipped_ops} saltate per conflitto)` : ""} · run #{result.run_id}. Vedi HISTORY per annullare.
        </span>
      )}
    </div>
  );
}
