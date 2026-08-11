"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getSettings, updateSettings, setRootTarget, runFingerprint, listProviders,
  type Settings, type RootTarget, type FingerprintResult, type ProviderInfo,
} from "@/lib/organize/api";
import { PageLayout } from "@/components/organize/page-layout";
import { Alert, Button, Loading, Spinner } from "@/components/organize/ui";
import { PathPickerButton, usePickerAvailability } from "@/components/organize/path-picker-button";
import { useI18n, useT } from "@/lib/organize/i18n";

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
function renderDest(targetRoot: string, folder: string, naming: string, sameFolderLabel: string): string {
  const base = targetRoot.trim() || sameFolderLabel;
  const folderPart = folder.trim() ? `${preview(folder)}/` : "";
  const namePart = preview(naming) || "{artist} - {title}";
  return `${base}/${folderPart}${namePart}.flac`;
}

export default function SettingsPage() {
  const { lang, setLang, t } = useI18n();
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
    catch (e) { setError(e instanceof Error ? e.message : t.common.error); }
  };
  const saveTarget = async (rootId: number, target: string) => {
    setError(null);
    try { setSettings(await setRootTarget(rootId, target.trim() || null)); }
    catch (e) { setError(e instanceof Error ? e.message : t.common.error); }
  };
  const onIdentify = async () => {
    setError(null);
    setFpBusy(true);
    try { setFpResult(await runFingerprint()); }
    catch (e) { setError(e instanceof Error ? e.message : t.common.error); }
    finally { setFpBusy(false); }
  };

  return (
    <PageLayout
      title="Settings"
      guide={<>
        <p>{t.settings.guideL1}</p>
        <p><b className="text-fg">{t.settings.guideTemplate}</b>{t.settings.guideL2mid}<b className="text-fg">{t.settings.guideDestination}</b>{t.settings.guideL2post}</p>
        <p>{t.settings.guideProviderPre}<b className="text-fg">{t.settings.guideProvider}</b>{t.settings.guideProviderPost}</p>
      </>}
    >
      <div className="flex max-w-2xl flex-col gap-6">
        <section className="flex flex-col gap-2">
          <h2 className="text-sm font-medium text-fg-strong">{t.settings.languageLabel}</h2>
          <div className="flex gap-2">
            <button
              type="button" onClick={() => setLang("it")} aria-pressed={lang === "it"}
              className={`border px-2 py-1 text-xs uppercase tracking-wider ${lang === "it" ? "border-border-strong bg-surface-2 text-fg-strong" : "border-border text-muted hover:text-fg"}`}
            >{t.settings.languageIt}</button>
            <button
              type="button" onClick={() => setLang("en")} aria-pressed={lang === "en"}
              className={`border px-2 py-1 text-xs uppercase tracking-wider ${lang === "en" ? "border-border-strong bg-surface-2 text-fg-strong" : "border-border text-muted hover:text-fg"}`}
            >{t.settings.languageEn}</button>
          </div>
        </section>

        {offline && <Alert>{t.common.backendOffline}</Alert>}
        {error && <Alert>{error}</Alert>}

        {!loaded && !offline && <Loading />}

        {settings && (
          <>
            <section className="flex flex-col gap-4">
              <div>
                <h2 className="text-sm font-medium text-fg-strong">{t.settings.organization}</h2>
                <p className="mt-1 text-xs text-faint">
                  {t.settings.orgIntroA}
                  <b className="text-muted">{t.settings.orgWhere}</b>{t.settings.orgIntroB}
                  <b className="text-muted">{t.settings.orgSubfolders}</b>{t.settings.orgIntroC}
                  <b className="text-muted">{t.settings.orgName}</b>{t.settings.orgIntroD}
                </p>
              </div>

              <label className="block">
                <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">{t.settings.tplNameLabel}</span>
                <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                  value={naming} onChange={(e) => setNaming(e.target.value)} />
                <span className="mt-1.5 block text-xs text-faint">{t.settings.fieldsLabel} <span className="font-mono">{"{artist} {title} {album} {genre} {year} {label} {track_no}"}</span></span>
              </label>

              <label className="block">
                <span className="mb-1.5 block text-[10px] font-medium uppercase tracking-wider text-muted">{t.settings.tplFolderLabel}</span>
                <input className="w-full border border-border bg-surface px-3 py-2 text-sm text-fg-strong focus:border-border-strong focus:outline-none"
                  value={folder} onChange={(e) => setFolder(e.target.value)} />
                <span className="mt-1.5 block text-xs text-faint">{folder.trim() ? <>{t.settings.subfoldersLabel} <span className="text-ok">{preview(folder)}/</span></> : t.settings.noSubfolders}</span>
              </label>

              <div className="border border-border bg-surface p-3">
                <div className="mb-1.5 text-[10px] font-medium uppercase tracking-wider text-muted">{t.settings.pathPreview}</div>
                <div className="overflow-x-auto whitespace-nowrap font-mono text-[11px] leading-relaxed">
                  <div className="text-faint">{SAMPLE_SOURCE}</div>
                  <div className="text-muted">↓</div>
                  <div className="text-ok">{renderDest(settings.roots[0]?.target_root ?? "", folder, naming, t.settings.sameFolder)}</div>
                </div>
                <p className="mt-1.5 text-[10px] text-faint">{t.settings.previewHint}</p>
              </div>

              <Button variant="outline" size="sm" className="self-start" onClick={saveTemplates}>{t.settings.saveTemplates}</Button>

              <div>
                <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-muted">{t.settings.whereToOrganize}</div>
                <p className="mb-3 text-xs text-faint">
                  {t.settings.rootExplainA}<b className="text-muted">{t.settings.rootExplainRoot}</b>{t.settings.rootExplainB}<b className="text-muted">{t.settings.rootExplainSources}</b>{t.settings.rootExplainC}<b className="text-muted">{t.settings.rootExplainDest}</b>{t.settings.rootExplainD}<b className="text-muted">{t.settings.rootExplainEmpty}</b>{t.settings.rootExplainE}
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
  const t = useT();
  const label = status === "configured" ? t.settings.statusConfigured : status === "connected" ? t.settings.statusConnected : t.settings.statusMissing;
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
      <h2 className="text-sm font-medium text-fg-strong">{t.settings.providerTitle}</h2>
      <p className="mt-1 text-xs text-faint">{t.settings.providerHintPre}<span className="font-mono">backend/.env</span>{t.settings.providerHintPost}</p>
      <div className="mt-3 flex flex-col">
        {providers.map((p, i) => (
          <div key={p.key} className="border-t border-border py-4 first:border-t-0">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                  <span className="tnum text-[11px] text-faint">{String(i + 1).padStart(2, "0")}</span>
                  <span className="text-sm font-medium uppercase tracking-wide text-fg-strong">{p.name}</span>
                  <span className="text-[10px] uppercase tracking-wider text-muted">{t.settings.providersMeta[p.key]?.category ?? p.category}</span>
                </div>
                <p className="mt-1 max-w-xl text-xs text-faint">{t.settings.providersMeta[p.key]?.description ?? p.description}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5">
                  {p.env_vars.map((v) => (
                    <code key={v} className="border border-border bg-bg px-1.5 py-0.5 font-mono text-[10px] text-muted">{v}</code>
                  ))}
                  <a href={p.docs_url} target="_blank" rel="noreferrer" className="text-[10px] text-muted underline-offset-2 hover:text-fg hover:underline">docs ↗</a>
                  {p.key === "acoustid" && p.status === "configured" && (
                    <button
                      onClick={onIdentify} disabled={fpBusy}
                      className="border border-border px-1.5 py-0.5 text-[10px] text-fg hover:bg-elevated disabled:opacity-40"
                    >{fpBusy ? t.settings.identifyBusy : t.settings.identifyNow}</button>
                  )}
                </div>
                {p.key === "acoustid" && fpResult && (
                  <p className="mt-1.5 text-[10px] text-faint">
                    {t.settings.fpResult(fpResult.identified, fpResult.below_threshold, fpResult.not_found, fpResult.errors, fpResult.total)}
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
  const t = useT();
  const [savedTargetRoot, setSavedTargetRoot] = useState(root.target_root);
  const [target, setTarget] = useState(root.target_root ?? "");
  const [busy, setBusy] = useState(false);
  const pickerOk = usePickerAvailability();
  const [pickError, setPickError] = useState<string | null>(null);
  if (savedTargetRoot !== root.target_root) {
    setSavedTargetRoot(root.target_root);
    setTarget(root.target_root ?? "");
  }
  const save = async () => { setBusy(true); try { await onSave(root.id, target); } finally { setBusy(false); } };
  const moves = target.trim().length > 0;
  return (
    <div className="border border-border bg-surface p-3">
      <div className="flex flex-col gap-1">
        <span className="text-[9px] font-medium uppercase tracking-wider text-muted">{t.settings.rowSource}</span>
        <div className="truncate font-mono text-xs text-fg-strong" title={root.path}>{root.path}</div>
        {root.label && <div className="text-[10px] text-muted">{root.label}</div>}
      </div>

      <div className="mt-2.5 flex flex-col gap-1">
        <span className="text-[9px] font-medium uppercase tracking-wider text-muted">{t.settings.rowDestination}</span>
        <div className="flex items-center gap-2">
          <input
            className="w-full max-w-md border border-border bg-bg px-2 py-1 font-mono text-[11px] text-fg placeholder:text-faint focus:border-border-strong focus:outline-none"
            value={target} onChange={(e) => setTarget(e.target.value)}
            placeholder={t.settings.targetPlaceholder}
          />
          {pickerOk && (
            <PathPickerButton kind="folder" start={target} prompt={t.settings.rowDestination}
              onPick={(p) => { setPickError(null); setTarget(p); }}
              onError={setPickError} />
          )}
          <Button variant="outline" size="sm" disabled={busy} onClick={save}>{busy ? <Spinner /> : t.settings.save}</Button>
        </div>
        {pickError && <p className="mt-1 text-xs text-danger">{pickError}</p>}
      </div>

      <div className="mt-2 overflow-x-auto whitespace-nowrap text-[10px] text-faint">
        {moves ? t.settings.fileBecomes : t.settings.exampleInPlace}{" "}
        <span className="font-mono text-ok">{renderDest(target, folder, naming, t.settings.sameFolder)}</span>
      </div>
    </div>
  );
}
