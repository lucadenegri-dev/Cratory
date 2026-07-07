"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  listIssues, listSources, setIssueStatus, fixIssue, bulkIssues, aiSuggestTags, aiSuggestGenres,
  providerSuggest, acceptHighOverrides,
  type Issue, type ScanRoot,
} from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { IssuesTable } from "@/components/issues-table";
import { Alert, Button, Checkbox, EmptyState, Input, Modal, Select } from "@/components/ui";

export default function IssuesPage() {
  const { scan, rescan, startRescan } = useJobs();
  const [issues, setIssues] = useState<Issue[]>([]);
  const [roots, setRoots] = useState<ScanRoot[]>([]);
  const [offline, setOffline] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [genreBusy, setGenreBusy] = useState(false);
  const [providerBusy, setProviderBusy] = useState(false);
  const [aiNote, setAiNote] = useState<string | null>(null);

  const [rescanFolder, setRescanFolder] = useState("");
  const [rescanGenre, setRescanGenre] = useState("");
  const [rescanFields, setRescanFields] = useState<string[]>(["genre"]);
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

  const onProviderSuggest = async () => {
    setActionError(null);
    setAiNote(null);
    setProviderBusy(true);
    try {
      const r = await providerSuggest();
      if (!r.configured) {
        setActionError("Configura le chiavi provider (MusicBrainz/Discogs) nel backend.");
      } else {
        load();
        setAiNote(
          `${r.suggested} suggerimenti da provider${r.fingerprinted > 0 ? ` (${r.fingerprinted} via fingerprint)` : ""}${r.unresolved > 0 ? `, ${r.unresolved} non trovati` : ""}${r.acoustid_available ? "" : " — fingerprint off, solo match testuale"} — rivedi e accetta col ✓.`,
        );
      }
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Errore");
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
      fields: rescanFields.length ? rescanFields : ["genre"],
      include_accepted: inclAccepted,
      include_dismissed: inclDismissed,
    }).catch((e) => setActionError(e instanceof Error ? e.message : "Errore"));
  };

  const onAcceptHigh = () =>
    act(async () => {
      const r = await acceptHighOverrides();
      setAiNote(`${r.updated} proposte ad alta confidenza accettate → andranno nel PLAN.`);
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
          ? `Rescan: ${r.proposed_high} proposte alta confidenza, ${r.proposed_text} testuali su ${r.scanned} tracce${r.acoustid_available ? "" : " (fingerprint off: nessuna alta confidenza)"}.`
          : "Rescan completato.",
      );
    }
    if (prevRescan.current === "running" && rescan.status === "error") {
      setActionError(rescan.error || "Rescan fallito");
    }
    prevRescan.current = rescan.status;
  }, [rescan.status, rescan.result, rescan.error, load]);

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
    (!needle ||
      (i.artist || "").toLowerCase().includes(needle) ||
      (i.title || "").toLowerCase().includes(needle) ||
      i.file_path.toLowerCase().includes(needle)),
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
      marginalia={<Marginalia total={issues.length} bySev={bySev} byType={byType} accepted={accepted} />}
      guide={<>
        <p>Problemi e proposte sui tag dei tuoi file.</p>
        <p>Riempi le proposte con AI o Provider, poi <b className="text-fg">✓ accetta</b> (va nel PLAN) o <b className="text-fg">✕ ignora</b>.</p>
        <p><b className="text-fg">Conf.</b>: alta = match certo (fingerprint), testuale = da rivedere.</p>
      </>}
    >
      <div className="flex flex-col gap-3">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}
        {actionError && <Alert>{actionError}</Alert>}
        {aiNote && <Alert tone="info">{aiNote}</Alert>}

        {/* filtri: a tutta larghezza */}
        <div className="grid grid-cols-2 gap-2 text-xs sm:grid-cols-3 lg:grid-cols-6">
          <Select value={sev} onChange={(e) => setSev(e.target.value)} className="h-8 text-xs">
            <option value="">severità: tutte</option>
            <option value="error">error</option>
            <option value="warning">warning</option>
            <option value="info">info</option>
          </Select>
          <Select value={type} onChange={(e) => setType(e.target.value)} className="h-8 text-xs">
            <option value="">tipo: tutti</option>
            {types.map((t) => <option key={t} value={t}>{t}</option>)}
          </Select>
          <Select value={field} onChange={(e) => setField(e.target.value)} className="h-8 text-xs">
            <option value="">campo: tutti</option>
            {fields.map((f) => <option key={f} value={f}>{f}</option>)}
          </Select>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} className="h-8 text-xs">
            <option value="open">aperte</option>
            <option value="accepted">accettate</option>
            <option value="dismissed">ignorate</option>
            <option value="">tutti gli stati</option>
          </Select>
          <Select value={rootId} onChange={(e) => setRootId(e.target.value)} className="h-8 text-xs">
            <option value="">tutte le radici</option>
            {roots.map((r) => <option key={r.id} value={r.id}>{r.label || r.path}</option>)}
          </Select>
          <Input
            value={search} onChange={(e) => setSearch(e.target.value)}
            placeholder="cerca…" className="h-8 text-xs"
          />
        </div>

        {/* bottoni bianchi: sotto i filtri, sopra la sezione forza ricerca */}
        <div className="flex flex-wrap gap-1.5">
          <Button variant="primary" size="sm" onClick={onAiSuggest} disabled={aiBusy}>
            {aiBusy ? "AI…" : "Recupera Artista/Titolo con AI"}
          </Button>
          <Button variant="primary" size="sm" onClick={onAiGenres} disabled={genreBusy}>
            {genreBusy ? "AI…" : "Recupera Genere con AI"}
          </Button>
          <Button variant="primary" size="sm" onClick={onProviderSuggest} disabled={providerBusy}>
            {providerBusy ? "importo…" : "Importa metadati mancanti da Provider"}
          </Button>
        </div>

        {/* forza ricerca provider: toolbar orizzontale */}
        <div className="border border-border bg-surface p-3">
          <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted">forza ricerca provider</div>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <input
              className="h-8 w-40 border border-border bg-bg px-2 text-[11px] text-fg-strong placeholder:text-faint focus:border-border-strong focus:outline-none"
              placeholder="cartella (es. House)…" value={rescanFolder}
              onChange={(e) => setRescanFolder(e.target.value)} />
            <input
              className="h-8 w-40 border border-border bg-bg px-2 text-[11px] text-fg-strong placeholder:text-faint focus:border-border-strong focus:outline-none"
              placeholder="genere attuale (opz.)…" value={rescanGenre}
              onChange={(e) => setRescanGenre(e.target.value)} />
            <div className="flex flex-wrap gap-2 text-[11px] text-muted">
              {["genre", "album", "label", "year"].map((f) => (
                <label key={f} className="flex items-center gap-1">
                  <input type="checkbox" checked={rescanFields.includes(f)} onChange={() => toggleField(f)} />
                  {f}
                </label>
              ))}
            </div>
            <Button variant="primary" size="sm" onClick={() => setRescanModal(true)} disabled={rescanRunning}>
              {rescanRunning ? "importo…" : "Importa tutti i metadati da Provider"}
            </Button>
          </div>
        </div>

        <Modal
          open={rescanModal}
          onClose={() => setRescanModal(false)}
          title="Importa tutti i metadati da Provider"
          footer={<>
            <Button variant="ghost" size="sm" onClick={() => setRescanModal(false)}>Annulla</Button>
            <Button variant="primary" size="sm" onClick={onProviderRescan}>Avvia</Button>
          </>}
        >
          <p className="text-sm text-muted">
            Reinterroga i provider sulle tracce{" "}
            {rescanFolder ? <>in <b className="text-fg-strong">{rescanFolder}</b></> : "presenti"}
            {rescanGenre ? <> con genere <b className="text-fg-strong">{rescanGenre}</b></> : null}
            {" "}per i campi <b className="text-fg-strong">{(rescanFields.length ? rescanFields : ["genre"]).join(", ")}</b>.
            Un campo viene riproposto solo se differisce da quello già sul file.
          </p>
          <div className="mt-4 flex flex-col gap-3">
            <Checkbox label="Riconsidera anche le proposte già accettate" checked={inclAccepted} onChange={setInclAccepted} />
            <Checkbox label="Riconsidera anche le proposte ignorate" checked={inclDismissed} onChange={setInclDismissed} />
            <p className="text-xs text-faint">
              Di default tocca solo le proposte ancora aperte. Le riconsiderate tornano da rivedere (aperte), ma solo se il provider ha un valore diverso.
            </p>
          </div>
        </Modal>

        {/* azioni di massa sotto la sezione forza ricerca provider */}
        <div className="flex flex-wrap gap-1.5">
          <Button variant="outline" size="sm" onClick={onAcceptHigh}>✓ Accetta tutti alta confidenza</Button>
          <Button variant="outline" size="sm" onClick={acceptAllFixable}>✓ Accetta tutti i fixabili</Button>
          <Button variant="outline" size="sm" onClick={dismissAllInfo}>✕ Ignora tutti gli info</Button>
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

function Marginalia({ total, bySev, byType, accepted }: {
  total: number;
  bySev: Record<string, number>;
  byType: Record<string, number>;
  accepted: number;
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
    </div>
  );
}
