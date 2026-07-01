"use client";

import { useCallback, useEffect, useState } from "react";
import { getSettings, updateSettings, setRootTarget, type Settings, type RootTarget } from "@/lib/api";
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

export default function SettingsPage() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [naming, setNaming] = useState("");
  const [folder, setFolder] = useState("");
  const [cratory, setCratory] = useState("");

  const load = useCallback(() => {
    getSettings()
      .then((s) => {
        setSettings(s); setNaming(s.naming_template); setFolder(s.folder_template);
        setCratory(s.cratory_base_url ?? ""); setOffline(false);
      })
      .catch(() => setOffline(true));
  }, []);
  useEffect(() => { load(); }, [load]);

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
  const saveCratory = async () => {
    setError(null);
    try { setSettings(await updateSettings({ cratory_base_url: cratory.trim() })); }
    catch (e) { setError(e instanceof Error ? e.message : "Errore"); }
  };

  return (
    <PageLayout title="Settings">
      <div className="flex max-w-2xl flex-col gap-6">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}
        {error && <Alert>{error}</Alert>}

        {settings && (
          <>
            <label className="block">
              <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">template nome file</span>
              <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                value={naming} onChange={(e) => setNaming(e.target.value)} />
              <span className="mt-1.5 block text-xs text-faint">anteprima: <span className="text-ok">{preview(naming) || "—"}.flac</span></span>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">template cartelle</span>
              <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                value={folder} onChange={(e) => setFolder(e.target.value)} />
              <span className="mt-1.5 block text-xs text-faint">{folder.trim() ? <>anteprima: <span className="text-ok">{preview(folder)}/</span></> : "vuoto = niente sottocartelle"}</span>
            </label>

            <Button variant="outline" size="sm" className="self-start" onClick={saveTemplates}>salva template</Button>

            <label className="block">
              <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">cratory (bridge sola-lettura)</span>
              <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                value={cratory} onChange={(e) => setCratory(e.target.value)} placeholder="http://localhost:8000" />
              <span className="mt-1.5 block text-xs text-faint">vuoto = bridge disattivato. Suggerisce genere/label/anno/artista/titolo dalla libreria di Cratory (deve essere in esecuzione).</span>
            </label>

            <Button variant="outline" size="sm" className="self-start" onClick={saveCratory}>salva cratory</Button>

            <div>
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted">dove organizzare (target per radice)</div>
              <p className="mb-3 text-xs text-faint">vuoto = organizza nella stessa cartella del file. Un path assoluto sposta là i file di quella radice.</p>
              <div className="flex flex-col gap-2">
                {settings.roots.map((r) => <RootRow key={r.id} root={r} onSave={saveTarget} />)}
              </div>
            </div>
          </>
        )}
      </div>
    </PageLayout>
  );
}

function RootRow({ root, onSave }: { root: RootTarget; onSave: (rootId: number, target: string) => Promise<void> }) {
  const [savedTargetRoot, setSavedTargetRoot] = useState(root.target_root);
  const [target, setTarget] = useState(root.target_root ?? "");
  const [busy, setBusy] = useState(false);
  if (savedTargetRoot !== root.target_root) {
    setSavedTargetRoot(root.target_root);
    setTarget(root.target_root ?? "");
  }
  const save = async () => { setBusy(true); try { await onSave(root.id, target); } finally { setBusy(false); } };
  return (
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
  );
}
