"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Redo2, Trash2, Undo2 } from "lucide-react";
import {
  ApiError, addAlternatives, apiDelete, chooseAlternative, errText, fmtDuration, fmtDurationLong,
  getManualSet,
  addSource, createManualSet, draftMaterial, fillGap, getMaterial, groupRows, insertRows,
  moveBlock, moveRow, patchRow, redoSet, removeAlternative, removeRow, removeSource,
  renameBlock, setPairNote, splitBlock, undoSet,
  type ManualAlternative, type ManualBlock, type ManualRow, type ManualSet, type ManualTransition,
  type Material, type MaterialItem, type Source,
} from "@/lib/api";
import { Alert, Badge, Button, Card, CardHeader, Loading, Modal } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { MaterialPanel } from "@/components/set-builder/material-panel";
import { PathPanel } from "@/components/set-builder/path-panel";
import { DetailPanel, type SaveState } from "@/components/set-builder/detail-panel";
import { ComparePanel } from "@/components/set-builder/compare-panel";
import { ReservePanel } from "@/components/set-builder/reserve-panel";
import { BenchPanel } from "@/components/set-builder/bench-panel";
import { ExportMenu } from "@/components/set-builder/export-menu";
import { FillGapPanel } from "@/components/set-builder/fill-gap-panel";
import { SourcesPanel } from "@/components/set-builder/sources-panel";
import { useT } from "@/lib/i18n";

export default function ManualSetPage() {
  // useSearchParams obbliga a un confine Suspense (build statico), come app/sets/detail/page.tsx.
  return <Suspense><ManualSetInner /></Suspense>;
}

function ManualSetInner() {
  const t = useT();
  const router = useRouter();
  // Senza `?id=` non e' un errore: e' una BOZZA. Il set nasce al primo gesto
  // che ha bisogno di una riga, non aprendo la pagina (deciso il 2026-09-19),
  // cosi' chi apre e chiude non lascia un set vuoto in archivio.
  const query_ = useSearchParams();
  const idDallaQuery = Number(query_.get("id") ?? "") || null;
  const playlistDallaQuery = Number(query_.get("playlist") ?? "") || null;
  const [setId, setSetId] = useState<number | null>(idDallaQuery);
  const [draftSources, setDraftSources] = useState<Source[]>(
    // `?playlist=` arriva da «Prepara un set» su una playlist: e' gia' scelta
    // nella bozza, e il nome lo riempie il pannello leggendo l'elenco.
    playlistDallaQuery && !idDallaQuery ? [{ playlist_id: playlistDallaQuery, name: null }] : []);
  const id = setId ?? 0;
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
  const [checkedRowIds, setCheckedRowIds] = useState<number[]>([]);
  const [fillingRowId, setFillingRowId] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const debounce = useRef<ReturnType<typeof setTimeout> | null>(null);
  const firstRun = useRef(true);

  const loadMaterial = useCallback(async (q = query, o = owned, u = unused, r = reserved) => {
    try {
      // La bozza non ha un set: il materiale si chiede per playlist.
      setMaterial(setId
        ? await getMaterial(setId, { q, owned: o, unused: u, reserved: r })
        : await draftMaterial({ playlist_ids: draftSources.map((x) => x.playlist_id), q, owned: o }));
    } catch (e) { setError(errText(e)); }
  }, [setId, draftSources, query, owned, unused, reserved]);

  const reloadAll = useCallback(async () => {
    setConflict(false);
    if (setId) {
      try { setSet(await getManualSet(setId)); setError(null); } catch (e) { setError(errText(e)); }
    }
    await loadMaterial();
  }, [setId, loadMaterial]);

  // Un effetto solo: al mount e a ogni cambio di set si ricarica tutto; su una
  // bozza le origini vivono nello stato locale, quindi cambiarle deve comunque
  // far richiedere il materiale.
  // eslint-disable-next-line react-hooks/exhaustive-deps, react-hooks/set-state-in-effect -- il backend e' l'external system; reloadAll cambia identita' a ogni render, e metterla fra le dipendenze farebbe ricaricare senza sosta
  useEffect(() => { void reloadAll(); }, [setId, draftSources]);

  useEffect(() => {
    if (firstRun.current) { firstRun.current = false; return; } // al montaggio carica gia' reloadAll
    if (debounce.current) clearTimeout(debounce.current);
    debounce.current = setTimeout(() => { void loadMaterial(query, owned, unused, reserved); }, 250);
    return () => { if (debounce.current) clearTimeout(debounce.current); };
  }, [query, owned, unused, reserved]); // eslint-disable-line react-hooks/exhaustive-deps

  /** Il set, creandolo se questa e' ancora una bozza. Unico punto in cui un set
   *  nasce: ci passa ogni mutazione, quindi non c'e' modo di dimenticarselo. */
  const assicuraSet = useCallback(async (): Promise<ManualSet> => {
    if (set) return set;
    const nuovo = await createManualSet({
      playlist_ids: draftSources.map((x) => x.playlist_id),
    });
    setSet(nuovo);
    setSetId(nuovo.id);
    // L'URL prende l'id: da qui in poi un ricaricamento non perde piu' niente.
    router.replace(`/sets/manual?id=${nuovo.id}`);
    return nuovo;
  }, [set, draftSources, router]);

  /** Applica una mutazione: la risposta e' la verita' (revision inclusa); su 409 chiede di ricaricare. */
  const mutate = useCallback(async (run: (rev: number, sid: number) => Promise<ManualSet>) => {
    try {
      // L'id arriva da qui e non dalla chiusura del render: su una bozza `id`
      // vale ancora 0 nell'istante in cui il set nasce (lo stato React non si e'
      // ancora aggiornato), e la mutazione finirebbe su /api/sets/0.
      const corrente = await assicuraSet();
      const next = await run(corrente.revision, corrente.id);
      setSet(next);
      setError(null);
      void loadMaterial();
      return next;
    } catch (e) {
      if (e instanceof ApiError && e.code === "set_revision_conflict") setConflict(true);
      else setError(errText(e));
      return null;
    }
  }, [assicuraSet, loadMaterial]);

  const onAdd = (item: MaterialItem) => mutate((rev, sid) => insertRows(sid, { expected_revision: rev, track_ids: [item.track.id], after_row_id: null }));
  const onGapAfter = (row: ManualRow) => mutate((rev, sid) => insertRows(sid, { expected_revision: rev, gap: true, after_row_id: row.id }));
  const onMove = (row: ManualRow, position: number) => mutate((rev, sid) => moveRow(sid, row.id, { expected_revision: rev, position }));
  const onRemove = (row: ManualRow) => {
    if (selectedRowId === row.id) setSelectedRowId(null);
    return mutate((rev, sid) => removeRow(sid, row.id, rev));
  };
  const onReserve = (item: MaterialItem) => mutate((rev, sid) => insertRows(sid, { expected_revision: rev, track_ids: [item.track.id], reserve: true }));
  const onAddAlternative = (item: MaterialItem) => selected && mutate((rev, sid) => addAlternatives(sid, selected.id, { expected_revision: rev, track_ids: [item.track.id] }));
  const onUseAlternative = (row: ManualRow, alt: ManualAlternative) => mutate((rev, sid) => chooseAlternative(sid, row.id, alt.id, { expected_revision: rev }));
  const onRemoveAlternative = (row: ManualRow, alt: ManualAlternative) => mutate((rev, sid) => removeAlternative(sid, row.id, alt.id, rev));
  const onToReserve = (row: ManualRow) => mutate((rev, sid) => moveRow(sid, row.id, { expected_revision: rev, position: 1, to_reserve: true }));
  const onToPath = (row: ManualRow) => mutate((rev, sid) => moveRow(sid, row.id, { expected_revision: rev, position: 1, to_reserve: false }));
  const onSavePlayBpm = (row: ManualRow, playBpm: number | null) =>
    // Solo la proprietà toccata: mandare anche `note` la riscriverebbe ogni volta.
    mutate((rev, sid) => patchRow(sid, row.id, { expected_revision: rev, play_bpm: playBpm }));
  /** Su una bozza le origini vivono nello stato locale: il set non c'e' ancora
   *  e crearlo per aggiungere una playlist sarebbe esattamente cio' che si sta
   *  evitando. Su un set vero passano dall'endpoint. */
  const onAddSource = async (playlistId: number) => {
    if (!set) {
      setDraftSources((prev) => prev.some((x) => x.playlist_id === playlistId)
        ? prev : [...prev, { playlist_id: playlistId, name: null }]);
      return;
    }
    await mutate((rev, sid) => addSource(sid, { expected_revision: rev, playlist_id: playlistId }));
  };
  const onRemoveSource = async (playlistId: number) => {
    if (!set) {
      setDraftSources((prev) => prev.filter((x) => x.playlist_id !== playlistId));
      return;
    }
    await mutate((rev, sid) => removeSource(sid, playlistId, rev));
  };

  const onSavePlannedSeconds = (row: ManualRow, seconds: number | null) =>
    mutate((rev, sid) => patchRow(sid, row.id, { expected_revision: rev, planned_seconds: seconds }));
  const onFillGap = async (row: ManualRow, count: number) => {
    const next = await mutate((rev, sid) => fillGap(sid, row.id, { expected_revision: rev, count }));
    if (next) setFillingRowId(null);   // un rifiuto lascia il pannello aperto
  };
  const onSavePairNote = (transition: ManualTransition, note: string) =>
    mutate((rev, sid) => setPairNote(sid, {
      expected_revision: rev, from_track_id: transition.from_track_id,
      to_track_id: transition.to_track_id, note: note.trim() || null,
    }));
  const onSaveNote = async (row: ManualRow, note: string) => {
    setSaveState("saving");
    const next = await mutate((rev, sid) => patchRow(sid, row.id, { expected_revision: rev, note: note.trim() || null }));
    setSaveState(next ? "saved" : "error");
  };

  const mainBlocks = set?.blocks.filter((b) => b.placement === "main") ?? [];
  const benchBlocks = set?.blocks.filter((b) => b.placement === "bench") ?? [];
  // NB: restano su `set`, non su `vista`: su una bozza non ci sono blocchi, e
  // `groupable` deve valere false invece di ragionare su una lista finta.

  /** Le righe spuntate, se formano un gruppo contiguo di UNA sola sequenza.
   *  Altrimenti non c'è niente da raggruppare e il comando non compare. */
  const groupable = (() => {
    if (checkedRowIds.length < 2) return null;
    const block = mainBlocks.find((b) => b.rows.some((r) => checkedRowIds.includes(r.id)));
    if (!block) return null;
    const indici = block.rows
      .map((r, i) => (checkedRowIds.includes(r.id) ? i : -1))
      .filter((i) => i >= 0);
    if (indici.length !== checkedRowIds.length) return null; // righe di sequenze diverse
    const contigue = indici.every((v, k) => k === 0 || v === indici[k - 1] + 1);
    if (!contigue) return null;
    return indici.map((i) => block.rows[i].id);
  })();

  const onGroup = async () => {
    if (!groupable) return;
    await mutate((rev, sid) => groupRows(sid, { expected_revision: rev, row_ids: groupable, name: null }));
    setCheckedRowIds([]);
  };
  const onCheck = (rowId: number) => setCheckedRowIds((prev) =>
    prev.includes(rowId) ? prev.filter((x) => x !== rowId) : [...prev, rowId]);
  const onRenameBlock = (block: ManualBlock, name: string) =>
    mutate((rev, sid) => renameBlock(sid, block.id, { expected_revision: rev, name: name.trim() || null }));
  const onMoveBlock = (block: ManualBlock, position: number) =>
    mutate((rev, sid) => moveBlock(sid, block.id, { expected_revision: rev, position }));
  const onToBench = (block: ManualBlock) =>
    mutate((rev, sid) => moveBlock(sid, block.id, { expected_revision: rev, position: benchBlocks.length + 1, to_bench: true }));
  const onBenchToPath = (block: ManualBlock) =>
    mutate((rev, sid) => moveBlock(sid, block.id, { expected_revision: rev, position: mainBlocks.length + 1, to_bench: false }));
  const onSplitBlock = (block: ManualBlock) =>
    mutate((rev, sid) => splitBlock(sid, block.id, { expected_revision: rev }));

  /** Annulla/ripeti. Un 409 «niente da annullare» non è un errore da mostrare:
   *  il pulsante era già spento, e lo stato vero arriva ricaricando. */
  const passoStorico = useCallback(async (avanti: boolean) => {
    if (!set) return;
    if (avanti ? !set.can_redo : !set.can_undo) return;
    try {
      setSet(await (avanti ? redoSet : undoSet)(id, { expected_revision: set.revision }));
      setError(null);
      setCheckedRowIds([]);
      void loadMaterial();
    } catch (e) {
      if (e instanceof ApiError && e.code === "set_revision_conflict") setConflict(true);
      else if (e instanceof ApiError && (e.code === "set_nothing_to_undo" || e.code === "set_nothing_to_redo")) void reloadAll();
      else setError(errText(e));
    }
  }, [set, id, loadMaterial, reloadAll]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "z" || !(e.metaKey || e.ctrlKey)) return;
      // Dentro un campo di testo comanda l'annulla del browser: è la parola
      // appena scritta che il DJ vuole indietro, non il set.
      const el = e.target as HTMLElement | null;
      const tag = el?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || el?.isContentEditable) return;
      e.preventDefault();
      void passoStorico(e.shiftKey);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [passoStorico]);

  const doDelete = async () => {
    setConfirmDelete(false);
    try { await apiDelete(`/api/sets/${id}`); router.push("/sets"); }
    catch (e) { setError(errText(e)); }
  };

  /** Cosa disegna la pagina: il set vero, o una bozza vuota con le sue origini.
   *  Non e' un set finto da salvare — le mutazioni passano da `assicuraSet`,
   *  che e' l'unico punto in cui un set nasce davvero. */
  const vista: ManualSet = set ?? {
    id: 0, name: t.sets.manual.pageTitle, kind: "manual", revision: 0,
    sources: draftSources, notes: null,
    track_count: 0, total_file_seconds: 0, can_undo: false, can_redo: false,
    created_at: "", updated_at: "",
    blocks: [], reserve: [], transitions: [],
    duration: { seconds: 0, incomplete: false, unknown_rows: 0, open_gaps: 0 },
  };

  const rows = mainBlocks.flatMap((b) => b.rows);
  const selected = rows.find((r) => r.id === selectedRowId) ?? null;
  // Il confronto si chiude da se' quando la riga sparisce dal percorso.
  const compareRow = rows.find((r) => r.id === compareRowId) ?? null;

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
        {!set && <><Badge>{t.sets.manual.draftBadge}</Badge> <span>{t.sets.manual.draftHint}</span></>}
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
      {set && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={!set.can_undo} onClick={() => void passoStorico(false)}>
            <Undo2 size={15} /> {t.sets.manual.undoButton}
          </Button>
          <Button size="sm" variant="outline" disabled={!set.can_redo} onClick={() => void passoStorico(true)}>
            <Redo2 size={15} /> {t.sets.manual.redoButton}
          </Button>
          {groupable && (
            <Button size="sm" variant="outline" onClick={() => void onGroup()}>
              {t.sets.manual.groupButton}
            </Button>
          )}
          <ExportMenu set={set} />
          <span className="text-sm text-muted">
            {t.sets.manual.durationLabel}{" "}
            <span className="tnum text-fg">{fmtDurationLong(set.duration.seconds)}</span>
            {set.duration.incomplete && (
              <>
                {" "}· {t.sets.manual.durationIncomplete}{" "}
                <span className="text-faint">
                  ({t.sets.manual.durationIncompleteWhy(set.duration.unknown_rows, set.duration.open_gaps)})
                </span>
              </>
            )}
          </span>
        </div>
      )}
      {setId !== null && set === null && !error && <Loading />}
      {(set !== null || setId === null) && (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,1fr)]">
          <Card className="p-4"><CardHeader title={t.sets.manual.materialTitle} />
            <SourcesPanel sources={set ? vista.sources : draftSources}
              onAdd={(p) => void onAddSource(p)} onRemove={(p) => void onRemoveSource(p)} />
            <MaterialPanel material={material} query={query} owned={owned} unused={unused}
              reserved={reserved} onReserved={setReserved}
              onQuery={setQuery} onOwned={setOwned} onUnused={setUnused} onAdd={(it) => void onAdd(it)}
              onReserve={(it) => void onReserve(it)} onAddAlternative={(it) => void onAddAlternative(it)}
              canAddAlternative={selected !== null} />
          </Card>
          <Card className="p-4"><CardHeader title={t.sets.manual.pathTitle} />
            <PathPanel set={vista} selectedRowId={selectedRowId} checkedRowIds={checkedRowIds}
              onSelect={(rid) => { setSelectedRowId(rid); setSaveState("idle"); }} onCheck={onCheck}
              onMove={(r, p) => void onMove(r, p)} onRemove={(r) => void onRemove(r)} onGapAfter={(r) => void onGapAfter(r)}
              onToReserve={(r) => void onToReserve(r)}
              onRenameBlock={(b, n) => void onRenameBlock(b, n)} onMoveBlock={(b, p) => void onMoveBlock(b, p)}
              onToBench={(b) => void onToBench(b)} onSplitBlock={(b) => void onSplitBlock(b)}
              fillingRowId={fillingRowId} onStartFill={(r) => setFillingRowId(r ? r.id : null)}
              renderFill={(r) => (
                <FillGapPanel row={r} onFill={(x, n) => void onFillGap(x, n)}
                  onClose={() => setFillingRowId(null)} />
              )} />
            <BenchPanel blocks={benchBlocks} onToPath={(b) => void onBenchToPath(b)} />
            <ReservePanel rows={vista.reserve} onToPath={(r) => void onToPath(r)} onRemove={(r) => void onRemove(r)} />
          </Card>
          <Card className="p-4"><CardHeader title={t.sets.manual.detailTitle} />
            <DetailPanel row={selected} transitions={vista.transitions} saveState={saveState}
              onSaveNote={(r, n) => void onSaveNote(r, n)}
              onSavePlayBpm={(r, b) => void onSavePlayBpm(r, b)}
              onSavePlannedSeconds={(r, s) => void onSavePlannedSeconds(r, s)}
              onSavePairNote={(x, n) => void onSavePairNote(x, n)}
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
