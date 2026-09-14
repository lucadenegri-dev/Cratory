"use client";

import { useCallback, useEffect, useState } from "react";
import { getSettings, updateSettings, type Settings } from "@/lib/organize/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* La sezione Organize della pagina Impostazioni: i soli template di rinomina.
   Viene dalla pagina /organize/settings, assorbita in F5; lo switcher di lingua
   che stava lì è sparito come duplicato, e la lista provider è confluita nella
   lista "Servizi esterni" più in alto in questa stessa pagina (una fonte sola,
   /api/services/status). */

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

// Percorso di destinazione d'esempio combinando template cartelle + template
// nome, con i tag SAMPLE. F3b: la destinazione non è più per-radice — ogni
// Apply sposta dentro la Library, quindi la base dell'anteprima è fissa.
const SAMPLE_SOURCE = "…/Downloads/ANNA - Hidden Beauties.wav";
function renderDest(folder: string, naming: string, libraryLabel: string): string {
  const folderPart = folder.trim() ? `${preview(folder)}/` : "";
  const namePart = preview(naming) || "{artist} - {title}";
  return `${libraryLabel}/${folderPart}${namePart}.flac`;
}

export function OrganizeSection() {
  const t = useT();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [offline, setOffline] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [naming, setNaming] = useState("");
  const [folder, setFolder] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(() => {
    getSettings()
      .then((s) => {
        setSettings(s); setNaming(s.naming_template); setFolder(s.folder_template);
        setOffline(false);
      })
      .catch(() => setOffline(true))
      .finally(() => setLoaded(true));
  }, []);
  useEffect(() => { load(); }, [load]);

  const saveTemplates = async () => {
    setError(null); setSaving(true); setSaved(false);
    try { setSettings(await updateSettings({ naming_template: naming, folder_template: folder })); setSaved(true); }
    catch (e) { setError(e instanceof Error ? e.message : t.organize.common.error); }
    finally { setSaving(false); }
  };

  return (
    <div className="flex max-w-2xl flex-col gap-6">
      {offline && <Alert>{t.organize.common.backendOffline}</Alert>}
      {error && <Alert>{error}</Alert>}
      {!loaded && !offline && <Loading />}

      {settings && (
        <>
          <section className="flex flex-col gap-4">
            <div>
              <h2 className="text-sm font-medium text-fg-strong">{t.organize.settings.organization}</h2>
              <p className="mt-1 text-xs text-muted">{t.settings.organizationHint}</p>
            </div>

            <label className="block">
              <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">{t.organize.settings.tplNameLabel}</span>
              <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                value={naming} disabled={saving} onChange={(e) => { setNaming(e.target.value); setSaved(false); }} />
              <span className="mt-1.5 block text-xs text-muted">{t.organize.settings.fieldsLabel} <span className="font-mono">{"{artist} {title} {album} {genre} {year} {label} {track_no}"}</span></span>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">{t.organize.settings.tplFolderLabel}</span>
              <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                value={folder} disabled={saving} onChange={(e) => { setFolder(e.target.value); setSaved(false); }} />
              <span className="mt-1.5 block text-xs text-muted">{folder.trim() ? <>{t.organize.settings.subfoldersLabel} <span className="text-fg">{preview(folder)}/</span></> : t.organize.settings.noSubfolders}</span>
            </label>

            <div className="border border-border bg-surface p-3">
              <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted">{t.organize.settings.pathPreview}</div>
              <div className="break-words font-mono text-[11px] leading-relaxed">
                <div className="text-muted">{SAMPLE_SOURCE}</div>
                <div className="text-muted">↓</div>
                <div className="text-fg">{renderDest(folder, naming, t.organize.files.library)}</div>
              </div>
              <p className="mt-1.5 text-xs text-muted">{t.organize.settings.previewHint}</p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button variant="outline" size="sm" disabled={saving || (naming === settings.naming_template && folder === settings.folder_template)} onClick={saveTemplates}>{t.organize.settings.saveTemplates}</Button>
              {saved && <span role="status" className="text-xs text-muted">{t.settings.savedLabel}</span>}
            </div>

            <p className="text-xs text-muted">{t.organize.settings.foldersNote}</p>
          </section>
        </>
      )}
    </div>
  );
}
