"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getSettings, updateSettings, setRootTarget, fingerprintStatus, runFingerprint,
  type Settings, type RootTarget, type FingerprintStatus, type FingerprintResult,
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
  const [fpStatus, setFpStatus] = useState<FingerprintStatus | null>(null);
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
  useEffect(() => { fingerprintStatus().then(setFpStatus).catch(() => {}); }, []);

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
                <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted">dove organizzare — destinazione per radice</div>
                <p className="mb-3 text-xs text-faint">
                  Per ogni cartella sorgente, dove finiscono i file organizzati.
                  <b className="text-muted"> Vuoto</b> = restano nella loro cartella (solo rinomina).
                  Un <b className="text-muted">path assoluto</b> (es. <span className="font-mono">/Users/tu/Music/Library</span>)
                  li sposta lì, dentro le sottocartelle del template.
                </p>
                <div className="flex flex-col gap-3">
                  {settings.roots.map((r) => (
                    <RootRow key={r.id} root={r} folder={folder} naming={naming} onSave={saveTarget} />
                  ))}
                </div>
              </div>
            </section>

            <div className="border border-border bg-surface p-4">
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted">provider testuali &amp; fingerprint</div>
              <p className="mb-3 text-xs text-faint">
                MusicBrainz/Discogs (metadati testuali) e AcoustID/Chromaprint (identità acustica → MBID).
              </p>
              <div className="mb-3 flex gap-4 text-xs">
                <span className={fpStatus?.configured ? "text-ok" : "text-faint"}>
                  AcoustID: {fpStatus ? (fpStatus.configured ? "configurato" : "non configurato") : "…"}
                </span>
                <span className={fpStatus?.fpcalc ? "text-ok" : "text-faint"}>
                  fpcalc: {fpStatus ? (fpStatus.fpcalc ? "disponibile" : "non trovato") : "…"}
                </span>
              </div>
              {fpStatus && !(fpStatus.configured && fpStatus.fpcalc) && (
                <p className="mb-3 text-xs text-faint">
                  Imposta ACOUSTID_API_KEY nel backend e installa fpcalc (Chromaprint) per abilitare l&apos;identificazione.
                </p>
              )}
              <Button
                variant="outline" size="sm"
                disabled={fpBusy || !fpStatus?.configured || !fpStatus?.fpcalc}
                onClick={onIdentify}
              >
                {fpBusy ? "identificazione in corso…" : "identifica ora"}
              </Button>
              {fpResult && (
                <p className="mt-2 text-xs text-faint">
                  {fpResult.identified} identificati, {fpResult.below_threshold} sotto soglia, {fpResult.not_found} non trovati
                  {fpResult.errors > 0 ? `, ${fpResult.errors} errori` : ""} (su {fpResult.total}).
                </p>
              )}
            </div>
          </>
        )}
      </div>
    </PageLayout>
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
  return (
    <div className="border border-border bg-surface p-2.5">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="truncate text-xs text-fg-strong" title={root.path}>{root.path}</div>
          <div className="text-[10px] text-muted">{root.label || "—"}</div>
        </div>
        <input
          className="w-64 border border-border bg-bg px-2 py-1 text-[11px] text-fg placeholder:text-faint focus:border-border-strong focus:outline-none"
          value={target} onChange={(e) => setTarget(e.target.value)} placeholder="(stessa cartella)"
        />
        <Button variant="outline" size="sm" disabled={busy} onClick={save}>salva</Button>
      </div>
      <div className="mt-1.5 overflow-x-auto whitespace-nowrap font-mono text-[10px] text-faint">
        → <span className="text-ok">{renderDest(target, folder, naming)}</span>
      </div>
    </div>
  );
}
