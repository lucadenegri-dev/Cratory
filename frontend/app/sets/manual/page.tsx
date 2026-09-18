"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Trash2 } from "lucide-react";
import {
  ApiError, addAlternatives, apiDelete, chooseAlternative, errText, fmtDuration, getManualSet,
  getMaterial, insertRows, moveRow, patchRow, removeAlternative, removeRow,
  type ManualAlternative, type ManualRow, type ManualSet, type Material, type MaterialItem,
} from "@/lib/api";
import { Alert, Badge, Button, Card, CardHeader, Loading, Modal } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { MaterialPanel } from "@/components/set-builder/material-panel";
import { PathPanel } from "@/components/set-builder/path-panel";
import { DetailPanel, type SaveState } from "@/components/set-builder/detail-panel";
import { ComparePanel } from "@/components/set-builder/compare-panel";
import { ReservePanel } from "@/components/set-builder/reserve-panel";
import { useT } from "@/lib/i18n";

export default function ManualSetPage() {
  // useSearchParams obbliga a un confine Suspense (build statico), come app/sets/detail/page.tsx.
  return <Suspense><ManualSetInner /></Suspense>;
}

function ManualSetInner() {
  const t = useT();
  const router = useRouter();
  const id = Number(useSearchParams().get("id") ?? "");
  const [set, setSet] = useState<ManualSet | null>(null);
  const [material, setMaterial] = useState<Material | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [selectedRowId, setSelectedRowId] = useState<number | null>(null);
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [query, setQuery] = useState("");
  const [owned, setOwned] = useState(false);
  const [unused, setUnused] = useState(false);
  const [reserved, setReserved] = useState(false);
  const [compareRowId, setCompareRowId] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const firstRun = useRef(true);

  const loadMaterial = useCallback(async (q = query, o = owned, u = unused, r = reserved) => {
    if (!id) return;
    try { setMaterial(await getMaterial(id, { q, owned: o, unused: u, reserved: r })); } catch (e) { setError(errText(e)); }
  }, [id, query, owned, unused, reserved]);

  const reloadAll = useCallback(async () => {
    if (!id) return;
    setConflict(false);
    try { setSet(await getManualSet(id)); setError(null); } catch (e) { setError(errText(e)); }
    await loadMaterial();
  }, [id, loadMaterial]);

  // eslint-disable-next-line react-hooks/exhaustive-deps, react-hooks/set-state-in-effect -- il backend e' l'external system: al mount/cambio id si ricarica tutto da zero
  useEffect(() => { void reloadAll(); }, [id]);

  useEffect(() => {
    if (firstRun.current) { firstRun.current = false; return; } // al montaggio carica gia' reloadAll
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => { void loadMaterial(query, owned, unused, reserved); }, 250);
    return () => { if (debounce.current) clearTimeout(debounce.current); };
  }, [query, owned, unused, reserved]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Applica una mutazione: la risposta e' la verita' (revision inclusa); su 409 chiede di ricaricare. */
  const mutate = useCallback(async (run: (rev: number) => Promise<ManualSet>) => {
    if (!set) return null;
    try {
      const next = await run(set.revision);
      setSet(next);
      setError(null);
      void loadMaterial();
      return next;
    } catch (e) {
      if (e instanceof ApiError && e.code === "set_revision_conflict") setConflict(true);
      else setError(errText(e));
      return null;
    }
  }, [set, loadMaterial]);

  const onAdd = (item: MaterialItem) => mutate((rev) => insertRows(id, { expected_revision: rev, track_ids: [item.track.id], after_row_id: null }));
  const onGapAfter = (row: ManualRow) => mutate((rev) => insertRows(id, { expected_revision: rev, gap: true, after_row_id: row.id }));
  const onMove = (row: ManualRow, position: number) => mutate((rev) => moveRow(id, row.id, { expected_revision: rev, position }));
  const onRemove = (row: ManualRow) => {
    if (selectedRowId === row.id) setSelectedRowId(null);
    return mutate((rev) => removeRow(id, row.id, rev));
  };
  const onReserve = (item: MaterialItem) => mutate((rev) => insertRows(id, { expected_revision: rev, track_ids: [item.track.id], reserve: true }));
  const onAddAlternative = (item: MaterialItem) => selected && mutate((rev) => addAlternatives(id, selected.id, { expected_revision: rev, track_ids: [item.track.id] }));
  const onUseAlternative = (row: ManualRow, alt: ManualAlternative) => mutate((rev) => chooseAlternative(id, row.id, alt.id, { expected_revision: rev }));
  const onRemoveAlternative = (row: ManualRow, alt: ManualAlternative) => mutate((rev) => removeAlternative(id, row.id, alt.id, rev));
  const onToReserve = (row: ManualRow) => mutate((rev) => moveRow(id, row.id, { expected_revision: rev, position: 1, to_reserve: true }));
  const onToPath = (row: ManualRow) => mutate((rev) => moveRow(id, row.id, { expected_revision: rev, position: 1, to_reserve: false }));
  const onSaveNote = async (row: ManualRow, note: string) => {
    setSaveState("saving");
    const next = await mutate((rev) => patchRow(id, row.id, { expected_revision: rev, note: note.trim() || null }));
    setSaveState(next ? "saved" : "error");
  };

  const doDelete = async () => {
    setConfirmDelete(false);
    try { await apiDelete(`/api/sets/${id}`); router.push("/sets"); }
    catch (e) { setError(errText(e)); }
  };

  const rows = set?.blocks.filter((b) => b.placement === "main").flatMap((b) => b.rows) ?? [];
  const selected = rows.find((r) => r.id === selectedRowId) ?? null;
  // Il confronto si chiude da se' quando la riga sparisce dal percorso.
  const compareRow = rows.find((r) => r.id === compareRowId) ?? null;

  if (!id) return <PageLayout title={t.sets.manual.pageTitle}><Alert tone="danger">{t.sets.manual.notFound}</Alert></PageLayout>;

  const meta = set ? t.sets.manual.tracksMeta(set.track_count, fmtDuration(set.total_file_seconds)) : undefined;

  return (
    <PageLayout title={set?.name ?? t.sets.manual.pageTitle} meta={meta}
      action={set && (
        <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
          <Trash2 size={15} /> {t.sets.deleteSetButton}
        </Button>
      )}>
      <div className="mb-3 flex flex-wrap items-center gap-2 text-sm text-muted">
        <Link href="/sets" className="inline-flex items-center gap-1 hover:text-fg"><ArrowLeft size={14} /> {t.sets.backLink}</Link>
        <Badge>{t.sets.manual.manualBadge}</Badge>
        {set && <span>{set.source_playlist_name ? t.sets.manual.fromPlaylist(set.source_playlist_name) : t.sets.manual.noPlaylist}</span>}
      </div>
      {error && <div className="mb-3"><Alert tone="danger">⚠ {error}</Alert></div>}
      {conflict && (
        <div className="mb-3">
          <Alert tone="warning">
            <div className="font-medium">{t.sets.manual.conflictTitle}</div>
            <div className="text-sm">{t.sets.manual.conflictBody}</div>
            <Button size="sm" variant="outline" className="mt-2" onClick={() => void reloadAll()}>{t.sets.manual.reloadButton}</Button>
          </Alert>
        </div>
      )}
      {set === null && !error && <Loading />}
      {set && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,1fr)]">
          <Card className="p-4"><CardHeader title={t.sets.manual.materialTitle} />
            <MaterialPanel material={material} query={query} owned={owned} unused={unused}
              reserved={reserved} onReserved={setReserved}
              onQuery={setQuery} onOwned={setOwned} onUnused={setUnused} onAdd={(it) => void onAdd(it)}
              onReserve={(it) => void onReserve(it)} onAddAlternative={(it) => void onAddAlternative(it)}
              canAddAlternative={selected !== null} />
          </Card>
          <Card className="p-4"><CardHeader title={t.sets.manual.pathTitle} />
            <PathPanel set={set} selectedRowId={selectedRowId} onSelect={(rid) => { setSelectedRowId(rid); setSaveState("idle"); }}
              onMove={(r, p) => void onMove(r, p)} onRemove={(r) => void onRemove(r)} onGapAfter={(r) => void onGapAfter(r)}
              onToReserve={(r) => void onToReserve(r)} />
            <ReservePanel rows={set.reserve} onToPath={(r) => void onToPath(r)} onRemove={(r) => void onRemove(r)} />
          </Card>
          <Card className="p-4"><CardHeader title={t.sets.manual.detailTitle} />
            <DetailPanel row={selected} saveState={saveState} onSaveNote={(r, n) => void onSaveNote(r, n)}
              onUseAlternative={(r, a) => void onUseAlternative(r, a)}
              onRemoveAlternative={(r, a) => void onRemoveAlternative(r, a)}
              onCompare={(r) => setCompareRowId(r.id)} />
            {compareRow && (
              <ComparePanel row={compareRow} onClose={() => setCompareRowId(null)}
                onUse={(a) => void onUseAlternative(compareRow, a)} />
            )}
          </Card>
        </div>
      )}

      {/* Conferma eliminazione: unico modo per buttare via un set manuale
          creato per errore, non avendo un editor classico da aprire. */}
      {set && (
        <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title={t.sets.deleteModalTitle}
          footer={<><Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>{t.common.cancel}</Button><Button variant="danger" size="sm" onClick={() => void doDelete()}><Trash2 size={15} /> {t.common.delete}</Button></>}>
          <p className="text-sm text-muted">{t.sets.deleteConfirmBody(set.name)}</p>
        </Modal>
      )}
    </PageLayout>
  );
}
