"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  listIssues, listSources, setIssueStatus, fixIssue, bulkIssues, aiSuggestTags, aiSuggestGenres,
  providerSuggest, acceptStrongOverrides, detectRatings,
  type Issue, type ScanRoot,
} from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { IssuesTable, type GroupBy } from "@/components/issues-table";
import { Alert, Button, Checkbox, EmptyState, Input, Loading, Modal, Select, Spinner } from "@/components/ui";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

export default function IssuesPage() {
  const t = useT();
  const { scan, rescan, startRescan } = useJobs();
  const [issues, setIssues] = useState<Issue[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [roots, setRoots] = useState<ScanRoot[]>([]);
  const [offline, setOffline] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [genreBusy, setGenreBusy] = useState(false);
  const [providerBusy, setProviderBusy] = useState(false);
  const [ratingBusy, setRatingBusy] = useState(false);
  const [aiNote, setAiNote] = useState<string | null>(null);

  const [rescanFolder, setRescanFolder] = useState("");
  const [rescanGenre, setRescanGenre] = useState("");
  const [rescanFields, setRescanFields] = useState<string[]>(["genre"]);
  const [rescanCovers, setRescanCovers] = useState(false);
  const [rescanOnlyNew, setRescanOnlyNew] = useState(false);
  const [rescanModal, setRescanModal] = useState(false);
  const [inclAccepted, setInclAccepted] = useState(false);
  const [inclDismissed, setInclDismissed] = useState(false);
  const rescanRunning = rescan.status === "running";

  const [sev, setSev] = useState("");
  const [type, setType] = useState("");
  const [field, setField] = useState("");
  const [status, setStatus] = useState("open");
  const [rootId, setRootId] = useState("");
  const [search, setSearch] = useState("");
  const [onlyNew, setOnlyNew] = useState(false);
  const [groupBy, setGroupBy] = useState<GroupBy>("type");
  const [forceOpen, setForceOpen] = useState(false);

  const load = useCallback(() => {
    listIssues()
      .then((r) => { setIssues(r); setOffline(false); })
      .catch(() => setOffline(true))
      .finally(() => setLoaded(true));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { listSources().then(setRoots).catch(() => {}); }, []);
  useEffect(() => { if (scan.status === "done") load(); }, [scan.status, load]);

  const act = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try { await fn(); load(); }
    catch (e) { setActionError(e instanceof Error ? e.message : t.common.error); }
  };
  const onFix = (id: number, value: string) => act(() => fixIssue(id, value));
  const onAccept = (id: number) => act(() => setIssueStatus(id, "accepted"));
  const onDismiss = (id: number) => act(() => setIssueStatus(id, "dismissed"));
  const onReopen = (id: number) => act(() => setIssueStatus(id, "open"));
  const acceptAllFixable = () => act(() => bulkIssues({ status: "accepted" }));
  const dismissAllInfo = () => act(() => bulkIssues({ severity: "info", status: "dismissed" }));
  const onAcceptCovers = () => act(async () => {
    const r = await bulkIssues({ type: "missing_cover", status: "accepted" });
    setAiNote(t.issues.acceptCoversNote(r.updated));
  });
  const onAcceptGroup = (key: string) => act(() =>
    bulkIssues(groupBy === "severity"
      ? { severity: key, status: "accepted" }
      : { type: key, status: "accepted" }));

  const onAiSuggest = async () => {
    setActionError(null);
    setAiNote(null);
    setAiBusy(true);
    try {
      const r = await aiSuggestTags();
      if (!r.configured) {
        setActionError(t.issues.aiNotConfigured);
      } else {
        load();
        setAiNote(t.issues.aiTagsNote(r.suggested, r.unresolved));
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.common.error);
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
        setActionError(t.issues.aiNotConfigured);
      } else {
        load();
        setAiNote(t.issues.aiGenresNote(r.suggested, r.unresolved));
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.common.error);
    } finally {
      setGenreBusy(false);
    }
  };

  const onProviderSuggest = async () => {
    setActionError(null);
    setAiNote(null);
    setProviderBusy(true);
    try {
      const r = await providerSuggest();
      if (!r.configured) {
        setActionError(t.issues.providerNotConfigured);
      } else {
        load();
        setAiNote(t.issues.providerNote(r.suggested, r.covers, r.fingerprinted, r.unresolved, r.acoustid_available));
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.common.error);
    } finally {
      setProviderBusy(false);
    }
  };

  const toggleField = (f: string) =>
    setRescanFields((cur) => (cur.includes(f) ? cur.filter((x) => x !== f) : [...cur, f]));

  const onProviderRescan = () => {
    setActionError(null);
    setAiNote(null);
    setRescanModal(false);
    startRescan({
      folder: rescanFolder || null,
      genre: rescanGenre || null,
      fields: rescanFields,
      include_accepted: inclAccepted,
      include_dismissed: inclDismissed,
      covers: rescanCovers,
      only_new: rescanOnlyNew,
    }).catch((e) => setActionError(e instanceof Error ? e.message : t.common.error));
  };

  const onDetectRatings = async () => {
    setActionError(null);
    setAiNote(null);
    setRatingBusy(true);
    try {
      const r = await detectRatings();
      load();
      setAiNote(r.found > 0 ? t.issues.detectRatingsNote(r.found, r.created) : t.issues.detectRatingsNone);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.common.error);
    } finally {
      setRatingBusy(false);
    }
  };

  // Cerca la copertina da provider per TUTTI i file che non ne hanno (non solo
  // quelli con tag da sistemare): rescan cover-only su tutta la libreria.
  const onFetchAllCovers = () => {
    setActionError(null);
    setAiNote(null);
    startRescan({ fields: [], covers: true })
      .catch((e) => setActionError(e instanceof Error ? e.message : t.common.error));
  };

  const onAcceptHigh = () =>
    act(async () => {
      const r = await acceptStrongOverrides();
      setAiNote(t.issues.acceptHighNote(r.updated));
    });

  // Il rescan gira nel job globale (barra in basso): quando passa running→done
  // ricarico le issue e mostro il riepilogo; su errore lo segnalo.
  const prevRescan = useRef(rescan.status);
  useEffect(() => {
    if (prevRescan.current === "running" && rescan.status === "done") {
      load();
      const r = rescan.result;
      setAiNote(
        r
          ? t.issues.rescanNote(r.proposed_strong, r.proposed_medium, r.proposed_weak, r.scanned, r.acoustid_available, r.covers)
          : t.issues.rescanDone,
      );
    }
    if (prevRescan.current === "running" && rescan.status === "error") {
      setActionError(rescan.error || t.issues.rescanFailed);
    }
    prevRescan.current = rescan.status;
  }, [rescan.status, rescan.result, rescan.error, load, t]);

  const types = useMemo(() => [...new Set(issues.map((i) => i.type))].sort(), [issues]);
  const fields = useMemo(
    () => [...new Set(issues.map((i) => i.field).filter((f): f is string => !!f))].sort(),
    [issues],
  );

  const needle = search.trim().toLowerCase();
  const filtered = issues.filter((i) =>
    (!sev || i.severity === sev) &&
    (!type || i.type === type) &&
    (!field || i.field === field) &&
    (!status || i.status === status) &&
    (!rootId || i.root_id === Number(rootId)) &&
    (!onlyNew || i.is_new) &&
    (!needle ||
      (i.artist || "").toLowerCase().includes(needle) ||
      (i.title || "").toLowerCase().includes(needle) ||
      i.file_path.toLowerCase().includes(needle)),
  );

  const bySev: Record<string, number> = { error: 0, warning: 0, info: 0 };
  const byType: Record<string, number> = {};
  let accepted = 0;
  let openCovers = 0;
  for (const i of issues) {
    bySev[i.severity] = (bySev[i.severity] ?? 0) + 1;
    byType[i.type] = (byType[i.type] ?? 0) + 1;
    if (i.status === "accepted") accepted++;
    if (i.type === "missing_cover" && i.status === "open") openCovers++;
  }

  // Le tre sorgenti che riempiono le proposte vuote: bottone + spiegazione.
  const enrichSources = [
    { onClick: onAiSuggest, busy: aiBusy,
      label: aiBusy ? t.issues.aiBusy : t.issues.aiTagsBtn,
      desc: t.issues.enrichAiTagsDesc, tag: t.issues.enrichAi },
    { onClick: onAiGenres, busy: genreBusy,
      label: genreBusy ? t.issues.aiBusy : t.issues.aiGenresBtn,
      desc: t.issues.enrichAiGenresDesc, tag: t.issues.enrichAi },
    { onClick: onProviderSuggest, busy: providerBusy,
      label: providerBusy ? t.issues.providerImportBusy : t.issues.providerSuggestBtn,
      desc: t.issues.enrichProviderDesc, tag: t.issues.enrichProviderTag },
    { onClick: onFetchAllCovers, busy: rescanRunning,
      label: rescanRunning ? t.issues.providerImportBusy : t.issues.fetchCoversBtn,
      desc: t.issues.fetchCoversDesc, tag: t.issues.enrichProviderTag },
    { onClick: onDetectRatings, busy: ratingBusy,
      label: ratingBusy ? t.issues.aiBusy : t.issues.detectRatingsBtn,
      desc: t.issues.detectRatingsDesc, tag: t.issues.enrichLocal },
  ];

  return (
    <PageLayout
      title="Issues"
      meta={`${filtered.length} / ${issues.length}`}
      marginaliaTitle={t.issues.summary}
      marginalia={<Marginalia total={issues.length} bySev={bySev} byType={byType} accepted={accepted} />}
      guide={<>
        <p>{t.issues.guide1}</p>
        <p>{t.issues.guide2pre}<b className="text-fg">{t.issues.guide2accept}</b>{t.issues.guide2mid}<b className="text-fg">{t.issues.guide2dismiss}</b>{t.issues.guide2post}</p>
        <p><b className="text-fg">{t.issues.guide3label}</b>{t.issues.guide3post}</p>
      </>}
    >
      <div className="flex flex-col gap-3">
        {offline && <Alert>{t.common.backendOffline}</Alert>}
        {actionError && <Alert>{actionError}</Alert>}
        {aiNote && <Alert tone="info">{aiNote}</Alert>}

        {/* filtri: a tutta larghezza */}
        <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
          <Select value={sev} onChange={(e) => setSev(e.target.value)} className="h-8 text-xs">
            <option value="">{t.issues.sevAll}</option>
            <option value="error">error</option>
            <option value="warning">warning</option>
            <option value="info">info</option>
          </Select>
          <Select value={type} onChange={(e) => setType(e.target.value)} className="h-8 text-xs">
            <option value="">{t.issues.typeAll}</option>
            {types.map((ty) => <option key={ty} value={ty}>{ty}</option>)}
          </Select>
          <Select value={field} onChange={(e) => setField(e.target.value)} className="h-8 text-xs">
            <option value="">{t.issues.fieldAll}</option>
            {fields.map((f) => <option key={f} value={f}>{f}</option>)}
          </Select>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 text-xs">
            <option value="open">{t.issues.statusOpen}</option>
            <option value="accepted">{t.issues.statusAccepted}</option>
            <option value="dismissed">{t.issues.statusDismissed}</option>
            <option value="">{t.issues.statusAll}</option>
          </Select>
          <Select value={rootId} onChange={(e) => setRootId(e.target.value)} className="h-8 text-xs">
            <option value="">{t.issues.allRoots}</option>
            {roots.map((r) => <option key={r.id} value={r.id}>{r.label || r.path}</option>)}
          </Select>
          <Input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder={t.issues.searchPlaceholder} className="h-8 text-xs"
          />
        </div>

        {/* Pannello Enrich: le tre sorgenti di proposte, ciascuna con la sua
            spiegazione, + la ricerca forzata provider ripiegata (progressive
            disclosure) invece di una toolbar sempre aperta. */}
        <section className="border border-border bg-surface">
          <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-b border-border px-3 py-2">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted">{t.issues.enrichTitle}</span>
            <span className="text-[10px] text-muted">{t.issues.enrichHint}</span>
          </div>
          <ul className="divide-y divide-border">
            {enrichSources.map((s, i) => (
              <li key={i} className="flex flex-col gap-2 px-3 py-2.5 sm:flex-row sm:items-center sm:gap-3">
                <Button
                  variant="primary" size="sm" onClick={s.onClick} disabled={s.busy}
                  className="w-full shrink-0 justify-start sm:w-64"
                >{s.busy && <Spinner />}{s.label}</Button>
                <p className="text-[11px] leading-relaxed text-fg">
                  {s.desc}
                  <span className="ml-1.5 border border-border px-1 py-0.5 align-middle text-[9px] uppercase tracking-wider text-muted">{s.tag}</span>
                </p>
              </li>
            ))}
          </ul>
          <div className="border-t border-border">
            <button
              type="button"
              onClick={() => setForceOpen((v) => !v)}
              className="flex w-full items-center gap-2 px-3 py-2 text-[10px] font-medium uppercase tracking-wider text-muted transition-colors hover:text-fg focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-fg"
              aria-expanded={forceOpen}
            >
              <span className="w-3 text-faint">{forceOpen ? "▾" : "▸"}</span>
              {t.issues.forceLookupToggle}
            </button>
            {forceOpen && (
              <div className="border-t border-border px-3 py-3">
                <p className="mb-2.5 text-[11px] leading-relaxed text-fg">{t.issues.forceLookupHint}</p>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-xs">
                  <input
                    className="h-8 w-40 border border-border bg-bg px-2 text-[11px] text-fg-strong placeholder:text-faint focus:border-border-strong focus:outline-none"
                    placeholder={t.issues.folderPlaceholder} value={rescanFolder}
                    onChange={(e) => setRescanFolder(e.target.value)} />
                  <input
                    className="h-8 w-40 border border-border bg-bg px-2 text-[11px] text-fg-strong placeholder:text-faint focus:border-border-strong focus:outline-none"
                    placeholder={t.issues.currentGenrePlaceholder} value={rescanGenre}
                    onChange={(e) => setRescanGenre(e.target.value)} />
                  <div className="flex flex-wrap gap-2 text-[11px] text-fg">
                    {["genre", "album", "label", "year", "artist", "title"].map((f) => (
                      <label key={f} className="flex items-center gap-1">
                        <input type="checkbox" checked={rescanFields.includes(f)} onChange={() => toggleField(f)} />
                        {f}
                      </label>
                    ))}
                    <label className="flex items-center gap-1 text-ok">
                      <input type="checkbox" checked={rescanCovers} onChange={(e) => setRescanCovers(e.target.checked)} />
                      {t.issues.rescanCovers}
                    </label>
                    <label className="flex items-center gap-1" title={t.issues.newFilesTitle}>
                      <input type="checkbox" checked={rescanOnlyNew} onChange={(e) => setRescanOnlyNew(e.target.checked)} />
                      {t.issues.rescanOnlyNew}
                    </label>
                  </div>
                  <Button variant="outline" size="sm" onClick={() => setRescanModal(true)} disabled={rescanRunning}>
                    {rescanRunning && <Spinner />}{rescanRunning ? t.issues.providerImportBusy : t.issues.providerRescanBtn}
                  </Button>
                </div>
                <p className="mt-2.5 text-[11px] leading-relaxed text-muted">{t.issues.rewriteReviewNote}</p>
              </div>
            )}
          </div>
        </section>

        <Modal
          open={rescanModal}
          onClose={() => setRescanModal(false)}
          title={t.issues.providerRescanBtn}
          footer={<>
            <Button variant="ghost" size="sm" onClick={() => setRescanModal(false)}>{t.common.cancel}</Button>
            <Button variant="primary" size="sm" onClick={onProviderRescan}>{t.issues.modalStart}</Button>
          </>}
        >
          <p className="text-sm text-muted">
            {t.issues.modalBodyPre}
            {rescanFolder ? <>in <b className="text-fg-strong">{rescanFolder}</b></> : t.issues.modalBodyPresent}
            {rescanGenre ? <>{t.issues.modalBodyGenrePre}<b className="text-fg-strong">{rescanGenre}</b></> : null}
            {t.issues.modalBodyFieldsPre}<b className="text-fg-strong">{(rescanFields.length ? rescanFields : ["genre"]).join(", ")}</b>
            {t.issues.modalBodyPost}
          </p>
          <div className="mt-4 flex flex-col gap-3">
            <Checkbox label={t.issues.reconsiderAccepted} checked={inclAccepted} onChange={setInclAccepted} />
            <Checkbox label={t.issues.reconsiderDismissed} checked={inclDismissed} onChange={setInclDismissed} />
            <p className="text-xs text-faint">
              {t.issues.reconsiderHint}
            </p>
          </div>
        </Modal>

        {/* barra sopra la lista: azioni di massa a sinistra, raggruppamento a destra */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1.5">
            <Button variant="outline" size="sm" onClick={onAcceptHigh}>{t.issues.acceptHighBtn}</Button>
            <Button variant="outline" size="sm" onClick={acceptAllFixable}>{t.issues.acceptFixableBtn}</Button>
            <Button variant="outline" size="sm" onClick={dismissAllInfo}>{t.issues.dismissInfoBtn}</Button>
            {openCovers > 0 && (
              <Button variant="outline" size="sm" onClick={onAcceptCovers}>{t.issues.acceptCoversBtn}</Button>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setOnlyNew((v) => !v)}
              title={t.issues.newFilesTitle}
              aria-pressed={onlyNew}
              className={cn(
                "h-8 border px-2.5 text-[10px] font-medium uppercase tracking-wider transition-colors",
                onlyNew
                  ? "border-fg-strong bg-fg-strong text-bg"
                  : "border-border-strong text-muted hover:text-fg",
              )}
            >{t.issues.newFilesOnly}</button>
            <label className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-wider text-muted">
              {t.issues.groupByLabel}
              <Select
                value={groupBy}
                onChange={(e) => setGroupBy(e.target.value as GroupBy)}
                className="h-8 w-28 text-[11px]"
              >
                <option value="type">{t.issues.groupByType}</option>
                <option value="severity">{t.issues.groupBySeverity}</option>
                <option value="none">{t.issues.groupByNone}</option>
              </Select>
            </label>
          </div>
        </div>

        {!loaded ? (
          <Loading />
        ) : filtered.length === 0 && !offline ? (
          <EmptyState title={t.issues.emptyTitle}>
            {issues.length === 0 ? t.issues.emptyClean : t.issues.emptyFiltered}
          </EmptyState>
        ) : (
          <IssuesTable
            issues={filtered} groupBy={groupBy}
            onFix={onFix} onAccept={onAccept} onDismiss={onDismiss} onReopen={onReopen}
            onAcceptGroup={onAcceptGroup}
          />
        )}
      </div>
    </PageLayout>
  );
}

function Marginalia({ total, bySev, byType, accepted }: {
  total: number;
  bySev: Record<string, number>;
  byType: Record<string, number>;
  accepted: number;
}) {
  const t = useT();
  return (
    <div className="flex flex-col gap-4 text-xs">
      <div>
        <div className="tnum text-2xl leading-none text-fg-strong">{total}</div>
        <div className="mt-1 text-[10px] uppercase tracking-wider text-muted">{t.issues.statIssues}</div>
        <div className="mt-1 flex gap-3 text-[11px]">
          <span className="text-danger">{bySev.error ?? 0} {t.files.sevErr}</span>
          <span className="text-warning">{bySev.warning ?? 0} {t.files.sevWarn}</span>
          <span className="text-muted">{bySev.info ?? 0} {t.files.sevInfo}</span>
        </div>
      </div>
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">{t.issues.byType}</div>
        <div className="flex flex-col gap-1">
          {Object.entries(byType).sort((a, b) => b[1] - a[1]).map(([ty, n]) => (
            <div key={ty} className="flex justify-between"><span className="text-muted">{ty}</span><span className="tnum text-fg">{n}</span></div>
          ))}
        </div>
      </div>
      <div>
        <div className="text-[10px] uppercase tracking-wider text-muted">{t.issues.acceptedLabel}</div>
        <div className="mt-1 text-[11px] text-ok">{t.issues.acceptedNote(accepted)}</div>
      </div>
    </div>
  );
}
