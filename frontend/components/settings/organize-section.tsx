"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getSettings, updateSettings, runFingerprint, listProviders,
  type Settings, type FingerprintResult, type ProviderInfo,
} from "@/lib/organize/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";

/* La sezione Organize della pagina Impostazioni: template di rinomina e stato
   dei provider di metadati. Viene dalla pagina /organize/settings, assorbita in
   F5; lo switcher di lingua che stava lì è sparito come duplicato — quello di
   Cratory, più in alto in questa stessa pagina, fa la stessa cosa. */

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
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [fpResult, setFpResult] = useState<FingerprintResult | null>(null);
  const [fpBusy, setFpBusy] = useState(false);

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
  useEffect(() => { listProviders().then(setProviders).catch(() => {}); }, []);

  const saveTemplates = async () => {
    setError(null);
    try { setSettings(await updateSettings({ naming_template: naming, folder_template: folder })); }
    catch (e) { setError(e instanceof Error ? e.message : t.organize.common.error); }
  };
  const onIdentify = async () => {
    setError(null);
    setFpBusy(true);
    try { setFpResult(await runFingerprint()); }
    catch (e) { setError(e instanceof Error ? e.message : t.organize.common.error); }
    finally { setFpBusy(false); }
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
              <p className="mt-1 text-xs text-faint">
                {t.organize.settings.orgIntroA}
                <b className="text-muted">{t.organize.settings.orgSubfolders}</b>{t.organize.settings.orgIntroC}
                <b className="text-muted">{t.organize.settings.orgName}</b>{t.organize.settings.orgIntroD}
              </p>
            </div>

            <label className="block">
              <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">{t.organize.settings.tplNameLabel}</span>
              <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                value={naming} onChange={(e) => setNaming(e.target.value)} />
              <span className="mt-1.5 block text-xs text-faint">{t.organize.settings.fieldsLabel} <span className="font-mono">{"{artist} {title} {album} {genre} {year} {label} {track_no}"}</span></span>
            </label>

            <label className="block">
              <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">{t.organize.settings.tplFolderLabel}</span>
              <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                value={folder} onChange={(e) => setFolder(e.target.value)} />
              <span className="mt-1.5 block text-xs text-faint">{folder.trim() ? <>{t.organize.settings.subfoldersLabel} <span className="text-ok">{preview(folder)}/</span></> : t.organize.settings.noSubfolders}</span>
            </label>

            <div className="border border-border bg-surface p-3">
              <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted">{t.organize.settings.pathPreview}</div>
              <div className="overflow-x-auto whitespace-nowrap font-mono text-[11px] leading-relaxed">
                <div className="text-faint">{SAMPLE_SOURCE}</div>
                <div className="text-muted">↓</div>
                <div className="text-ok">{renderDest(folder, naming, t.organize.files.library)}</div>
              </div>
              <p className="mt-1.5 text-[10px] text-faint">{t.organize.settings.previewHint}</p>
            </div>

            <Button variant="outline" size="sm" className="self-start" onClick={saveTemplates}>{t.organize.settings.saveTemplates}</Button>

            <p className="text-xs text-faint">{t.organize.settings.foldersNote}</p>
          </section>

          <ProviderList
            providers={providers} fpResult={fpResult} fpBusy={fpBusy} onIdentify={onIdentify}
          />
        </>
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: ProviderInfo["status"] }) {
  const t = useT();
  const label = status === "configured" ? t.organize.settings.statusConfigured : status === "connected" ? t.organize.settings.statusConnected : t.organize.settings.statusMissing;
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
  const t = useT();
  return (
    <section>
      <h2 className="text-sm font-medium text-fg-strong">{t.organize.settings.providerTitle}</h2>
      <p className="mt-1 text-xs text-faint">{t.organize.settings.providerHintPre}<span className="font-mono">backend/.env</span>{t.organize.settings.providerHintPost}</p>
      <div className="mt-3 flex flex-col">
        {providers.map((p, i) => (
          <div key={p.key} className="border-t border-border py-4 first:border-t-0">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="tnum text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</span>
                  <span className="text-sm font-medium uppercase tracking-wide text-fg-strong">{p.name}</span>
                  <span className="text-[10px] uppercase tracking-wider text-muted">{t.organize.settings.providersMeta[p.key]?.category ?? p.category}</span>
                </div>
                <p className="mt-1 max-w-xl text-xs text-faint">{t.organize.settings.providersMeta[p.key]?.description ?? p.description}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {p.env_vars.map((v) => (
                    <code key={v} className="border border-border bg-bg px-1.5 py-0.5 font-mono text-[10px] text-muted">{v}</code>
                  ))}
                  <a href={p.docs_url} target="_blank" rel="noreferrer" className="text-[10px] text-muted underline-offset-2 hover:text-fg hover:underline">docs ↗</a>
                  {p.key === "acoustid" && p.status === "configured" && (
                    <button
                      onClick={onIdentify} disabled={fpBusy}
                      className="border border-border px-1.5 py-0.5 text-[10px] text-fg hover:bg-elevated disabled:opacity-40"
                    >{fpBusy ? t.organize.settings.identifyBusy : t.organize.settings.identifyNow}</button>
                  )}
                </div>
                {p.key === "acoustid" && fpResult && (
                  <p className="mt-1.5 text-[10px] text-faint">
                    {t.organize.settings.fpResult(fpResult.identified, fpResult.below_threshold, fpResult.not_found, fpResult.errors, fpResult.total)}
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
