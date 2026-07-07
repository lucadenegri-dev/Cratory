"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getSettings, updateSettings, setRootTarget, runFingerprint, listProviders,
  type Settings, type RootTarget, type FingerprintResult, type ProviderInfo,
} from "@/lib/api";
import { PageLayout } from "@/components/page-layout";
import { Alert, Button } from "@/components/ui";

// Valori d'esempio per l'anteprima client-side (approssimata: la resa reale con
// sanitizzazione è lato planner).
const SAMPLE: Record<string, string> = {
  artist: "ANNA", title: "Hidden Beauties", album: "Hidden Beauties",
  album_artist: "ANNA", genre: "House", year: "2023", label: "Diynamic",
  track_no: "1", comment: "",
};
function preview(tpl: string): string {
  return tpl.replace(/\{(\w+)\}/g, (_, k) => SAMPLE[k] ?? `{${k}}`);
}

// Percorso di destinazione d'esempio combinando target radice + template
// cartelle + template nome, con i tag SAMPLE. Serve a mostrare "dove finisce"
// davvero un file (anteprima approssimata; la resa reale è lato planner).
const SAMPLE_SOURCE = "…/Downloads/ANNA - Hidden Beauties.wav";
function renderDest(targetRoot: string, folder: string, naming: string): string {
  const base = targetRoot.trim() || "(stessa cartella del file)";
  const folderPart = folder.trim() ? `${preview(folder)}/` : "";
  const namePart = preview(naming) || "{artist} - {title}";
  return `${base}/${folderPart}${namePart}.flac`;
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [naming, setNaming] = useState("");
  const [folder, setFolder] = useState("");
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [fpResult, setFpResult] = useState<FingerprintResult | null>(null);
  const [fpBusy, setFpBusy] = useState(false);

  const load = useCallback(() => {
    getSettings()
      .then((s) => {
        setSettings(s); setNaming(s.naming_template); setFolder(s.folder_template);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { listProviders().then(setProviders).catch(() => {}); }, []);

  const saveTemplates = async () => {
    setError(null);
    try { setSettings(await updateSettings({ naming_template: naming, folder_template: folder })); }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
  };
  const saveTarget = async (rootId: number, target: string) => {
    setError(null);
    try { setSettings(await setRootTarget(rootId, target.trim() || null)); }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
  };
  const onIdentify = async () => {
    setError(null);
    setFpBusy(true);
    try { setFpResult(await runFingerprint()); }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
    finally { setFpBusy(false); }
  };

  return (
    <PageLayout title="Settings">
      <div className="flex max-w-2xl flex-col gap-6">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}
        {error && <Alert>{error}</Alert>}

        {settings && (
          <>
            <section className="flex flex-col gap-4">
              <div>
                <h2 className="text-sm font-medium text-fg-strong">Organizzazione</h2>
                <p className="mt-1 text-xs text-faint">
                  Applicando un PLAN ogni file viene spostato e rinominato in base a tre cose:
                  <b className="text-muted"> dove</b> finisce (destinazione per radice, in fondo),
                  in quali <b className="text-muted">sottocartelle</b> (template cartelle) e con che
                  <b className="text-muted"> nome</b> (template nome file).
                </p>
              </div>

              <label className="block">
                <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">template nome file</span>
                <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                  value={naming} onChange={(e) => setNaming(e.target.value)} />
                <span className="mt-1.5 block text-xs text-faint">campi: <span className="font-mono">{"{artist} {title} {album} {genre} {year} {label} {track_no}"}</span></span>
              </label>

              <label className="block">
                <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">template cartelle</span>
                <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                  value={folder} onChange={(e) => setFolder(e.target.value)} />
                <span className="mt-1.5 block text-xs text-faint">{folder.trim() ? <>sottocartelle: <span className="text-ok">{preview(folder)}/</span></> : "vuoto = niente sottocartelle"}</span>
              </label>

              <div className="border border-border bg-surface p-3">
                <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted">anteprima percorso</div>
                <div className="overflow-x-auto whitespace-nowrap font-mono text-[11px] leading-relaxed">
                  <div className="text-faint">{SAMPLE_SOURCE}</div>
                  <div className="text-muted">↓</div>
                  <div className="text-ok">{renderDest(settings.roots[0]?.target_root ?? "", folder, naming)}</div>
                </div>
                <p className="mt-1.5 text-[10px] text-faint">esempio con la destinazione della prima radice — ognuna può avere la sua (sotto).</p>
              </div>

              <Button variant="outline" size="sm" className="self-start" onClick={saveTemplates}>salva template</Button>

              <div>
                <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted">dove organizzare — una destinazione per radice</div>
                <p className="mb-3 text-xs text-faint">
                  Una <b className="text-muted">radice</b> è una cartella che hai aggiunto in <b className="text-muted">Sources</b> e che
                  DjOrganizer scansiona. Per ognuna imposti una <b className="text-muted">destinazione</b>: dove spostare i suoi file
                  una volta organizzati. Lascia <b className="text-muted">vuoto</b> per tenerli dove sono (solo rinomina, niente spostamento).
                </p>
                <div className="flex flex-col gap-3">
                  {settings.roots.map((r) => (
                    <RootRow key={r.id} root={r} folder={folder} naming={naming} onSave={saveTarget} />
                  ))}
                </div>
              </div>
            </section>

            <ProviderList
              providers={providers} fpResult={fpResult} fpBusy={fpBusy} onIdentify={onIdentify}
            />
          </>
        )}
      </div>
    </PageLayout>
  );
}

function StatusBadge({ status }: { status: ProviderInfo["status"] }) {
  const label = status === "configured" ? "configurato" : status === "connected" ? "collegato" : "mancante";
  return (
    <span className={`shrink-0 text-[10px] uppercase tracking-wider ${status === "missing" ? "text-faint" : "text-ok"}`}>
      {label}
    </span>
  );
}

function ProviderList({ providers, fpResult, fpBusy, onIdentify }: {
  providers: ProviderInfo[];
  fpResult: FingerprintResult | null;
  fpBusy: boolean;
  onIdentify: () => void;
}) {
  return (
    <section>
      <h2 className="text-sm font-medium text-fg-strong">Provider</h2>
      <p className="mt-1 text-xs text-faint">Chiavi e binari nel file <span className="font-mono">backend/.env</span> (o nel PATH per fpcalc).</p>
      <div className="mt-3 flex flex-col">
        {providers.map((p, i) => (
          <div key={p.key} className="border-t border-border py-4 first:border-t-0">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="tnum text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</span>
                  <span className="text-sm font-medium uppercase tracking-wide text-fg-strong">{p.name}</span>
                  <span className="text-[10px] uppercase tracking-wider text-muted">{p.category}</span>
                </div>
                <p className="mt-1 max-w-xl text-xs text-faint">{p.description}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {p.env_vars.map((v) => (
                    <code key={v} className="border border-border bg-bg px-1.5 py-0.5 font-mono text-[10px] text-muted">{v}</code>
                  ))}
                  <a href={p.docs_url} target="_blank" rel="noreferrer" className="text-[10px] text-muted underline-offset-2 hover:text-fg hover:underline">docs ↗</a>
                  {p.key === "acoustid" && p.status === "configured" && (
                    <button
                      onClick={onIdentify} disabled={fpBusy}
                      className="border border-border px-1.5 py-0.5 text-[10px] text-fg hover:bg-elevated disabled:opacity-40"
                    >{fpBusy ? "identificazione…" : "identifica ora"}</button>
                  )}
                </div>
                {p.key === "acoustid" && fpResult && (
                  <p className="mt-1.5 text-[10px] text-faint">
                    {fpResult.identified} identificati, {fpResult.below_threshold} sotto soglia, {fpResult.not_found} non trovati
                    {fpResult.errors > 0 ? `, ${fpResult.errors} errori` : ""} (su {fpResult.total}).
                  </p>
                )}
              </div>
              <StatusBadge status={p.status} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function RootRow({ root, folder, naming, onSave }: {
  root: RootTarget;
  folder: string;
  naming: string;
  onSave: (rootId: number, target: string) => Promise<void>;
}) {
  const [savedTargetRoot, setSavedTargetRoot] = useState(root.target_root);
  const [target, setTarget] = useState(root.target_root ?? "");
  const [busy, setBusy] = useState(false);
  if (savedTargetRoot !== root.target_root) {
    setSavedTargetRoot(root.target_root);
    setTarget(root.target_root ?? "");
  }
  const save = async () => { setBusy(true); try { await onSave(root.id, target); } finally { setBusy(false); } };
  const moves = target.trim().length > 0;
  return (
    <div className="border border-border bg-surface p-3">
      <div className="flex flex-col gap-1">
        <span className="text-[9px] font-medium uppercase tracking-wider text-muted">sorgente — cartella scansionata (da Sources)</span>
        <div className="truncate font-mono text-xs text-fg-strong" title={root.path}>{root.path}</div>
        {root.label && <div className="text-[10px] text-muted">{root.label}</div>}
      </div>

      <div className="mt-2.5 flex flex-col gap-1">
        <span className="text-[9px] font-medium uppercase tracking-wider text-muted">destinazione — dove spostare i file organizzati</span>
        <div className="flex items-center gap-2">
          <input
            className="w-full max-w-md border border-border bg-bg px-2 py-1 font-mono text-[11px] text-fg placeholder:text-faint focus:border-border-strong focus:outline-none"
            value={target} onChange={(e) => setTarget(e.target.value)}
            placeholder="vuoto = restano nella cartella sorgente (solo rinomina)"
          />
          <Button variant="outline" size="sm" disabled={busy} onClick={save}>salva</Button>
        </div>
      </div>

      <div className="mt-2 overflow-x-auto whitespace-nowrap text-[10px] text-faint">
        {moves ? "un file di questa radice diventa:" : "esempio (rinominato sul posto):"}{" "}
        <span className="font-mono text-ok">{renderDest(target, folder, naming)}</span>
      </div>
    </div>
  );
}
