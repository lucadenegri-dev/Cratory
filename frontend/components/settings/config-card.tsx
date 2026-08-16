"use client";

import { useCallback, useEffect, useState } from "react";
import {
  errText, getConfigSettings, patchConfigSettings, setDownloadSlots, setLibraryShare, startLibraryIndex,
  type ConfigPatch, type ConfigSettings,
} from "@/lib/api";
import { Alert, Badge, Button, CardHeader, Checkbox, Field, Input, Loading, Spinner } from "@/components/ui";
import { PathPickerButton, usePickerAvailability } from "@/components/path-picker-button";
import { useJobs } from "@/components/jobs-provider";
import { useT } from "@/lib/i18n";

const CONFIG_FIELDS = [
  "library_root", "archive_root", "slskd_download_dir", "slskd_url", "slskd_config_path",
] as const;
type ConfigFieldKey = (typeof CONFIG_FIELDS)[number];

// quali campi hanno "Sfoglia…" e con che dialog; slskd_url è un URL di
// rete, niente pulsante.
const PICK_KIND: Partial<Record<ConfigFieldKey, "folder" | "file">> = {
  library_root: "folder",
  archive_root: "folder",
  slskd_download_dir: "folder",
  slskd_config_path: "file",
};

export function ConfigCard() {
  const t = useT();
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [shareMsg, setShareMsg] = useState<string | null>(null);
  const pickerOk = usePickerAvailability();

  const hydrate = useCallback((c: ConfigSettings) => {
    setConfig(c);
    setDraft(Object.fromEntries(CONFIG_FIELDS.map((k) => [k, c[k].value])));
    setWarning(c.warning);
  }, []);

  const reloadConfig = useCallback(() => {
    getConfigSettings().then(hydrate).catch((e) => setError(errText(e)));
  }, [hydrate]);

  useEffect(reloadConfig, [reloadConfig]);

  const FIELD_LABEL: Record<ConfigFieldKey, string> = {
    library_root: t.settings.fieldLibraryRoot,
    archive_root: t.settings.fieldArchiveRoot,
    slskd_download_dir: t.settings.fieldDownloadsDir,
    slskd_url: t.settings.fieldSlskdUrl,
    slskd_config_path: t.settings.fieldSlskdConfig,
  };

  const dirty = config ? CONFIG_FIELDS.some((k) => draft[k] !== config[k].value) : false;

  const save = async () => {
    if (!config) return;
    const patch: ConfigPatch = {};
    for (const k of CONFIG_FIELDS) if (draft[k] !== config[k].value) patch[k] = draft[k];
    setSaving(true); setError(null); setSaved(false);
    try {
      hydrate(await patchConfigSettings(patch));
      setSaved(true); setTimeout(() => setSaved(false), 1500);
    } catch (e) { setError(errText(e)); }
    finally { setSaving(false); }
  };

  const toggleShare = async (enabled: boolean) => {
    setShareBusy(true); setError(null); setShareMsg(null);
    try {
      const r = await setLibraryShare(enabled);
      setConfig((c) => (c ? { ...c, share_library: r.share_library } : c));
      setShareMsg(!enabled ? t.settings.shareOff
        : r.rescan ? t.settings.shareOnRescan : t.settings.shareOnPending);
    } catch (e) { setError(errText(e)); }
    finally { setShareBusy(false); }
  };

  if (!config) {
    return (
      <div className="border border-border p-5">
        {error ? <Alert tone="danger">⚠ {error}</Alert> : <Loading />}
      </div>
    );
  }

  return (
    <div className="border border-border">
      <CardHeader title={t.settings.configHeading} subtitle={t.settings.configSubtitle} />
      <div className="space-y-4 p-5">
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {warning && <Alert tone="warning">{warning}</Alert>}
        {CONFIG_FIELDS.map((k) => {
          const f = config[k];
          const unchanged = draft[k] === f.value;
          const pickKind = PICK_KIND[k]; // variabile locale: TS non restringe PICK_KIND[k] tra due accessi
          return (
            <Field key={k}
              label={
                <span className="flex flex-wrap items-center gap-2">
                  {FIELD_LABEL[k]}
                  {f.source === "db" && <Badge tone="info">{t.settings.overrideBadge}</Badge>}
                  {unchanged && !f.valid && <Badge tone="danger">{f.detail}</Badge>}
                </span>
              }
              hint={!unchanged ? t.settings.unsavedHint : f.valid ? (f.detail ?? undefined) : undefined}>
              <div className="flex items-center gap-2">
                <Input className="flex-1" value={draft[k] ?? ""}
                  onChange={(e) => setDraft((d) => ({ ...d, [k]: e.target.value }))} />
                {pickerOk && pickKind && (
                  <PathPickerButton kind={pickKind} start={draft[k]} prompt={FIELD_LABEL[k]}
                    onPick={(p) => setDraft((d) => ({ ...d, [k]: p }))}
                    onError={setError} />
                )}
              </div>
            </Field>
          );
        })}
        <Button size="sm" onClick={save} disabled={saving || !dirty}>
          {saving ? <Spinner /> : null} {saved ? t.settings.savedLabel : t.settings.saveButton}
        </Button>

        <div className="border-t border-border pt-4">
          <Checkbox label={t.settings.shareLibraryLabel} checked={config.share_library}
            disabled={shareBusy} onChange={toggleShare} />
          <p className="mt-1.5 text-xs text-muted">{t.settings.shareLibraryHint}</p>
          {shareMsg && <p className="mt-1.5 text-xs text-fg">{shareMsg}</p>}
        </div>

        <div className="border-t border-border">
          <DownloadSlotsSection value={config.download_slots} reload={reloadConfig} />
        </div>

        <div className="border-t border-border pt-4">
          <LibraryIndexSection />
        </div>
      </div>
    </div>
  );
}

/** Quanti download Soulseek in parallelo (B-Task 6: la coda ha un pool di N
 *  slot). Salva su blur, non a ogni tasto; ignora un valore invariato o
 *  fuori scala 1-10 (il backend risponderebbe 422 con un numero che l'utente
 *  ha appena digitato). */
function DownloadSlotsSection({ value, reload }: { value: number; reload: () => void }) {
  const t = useT();
  const [slots, setSlots] = useState(value);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    if (slots === value || slots < 1 || slots > 10) return;
    try {
      await setDownloadSlots(slots);
      setError(null);
      reload();
    } catch (e) { setError(errText(e)); }
  };

  return (
    <div>
      {error && <div className="px-5 pt-3"><Alert tone="danger">⚠ {error}</Alert></div>}
      <label className="flex items-center gap-3 px-5 py-3 text-sm">
        <span className="flex-1">
          {t.settings.downloadSlotsLabel}
          <span className="mt-0.5 block text-xs text-faint">{t.settings.downloadSlotsHint}</span>
        </span>
        <Input type="number" min={1} max={10} className="h-8 w-20"
          value={slots}
          onChange={(e) => setSlots(Number(e.target.value))}
          onBlur={() => void save()} />
      </label>
    </div>
  );
}

/* Indicizzazione della libreria canonica: vive dentro la card dei percorsi
   perche' LIBRARY_ROOT e "Indicizza ora" sono la stessa cosa vista da due
   lati (il path e l'azione che lo legge). Stato dal poller globale
   (JobsProvider): niente polling locale. */
function LibraryIndexSection() {
  const t = useT();
  const { libraryIndex: libJob, refresh } = useJobs();
  const [libError, setLibError] = useState<string | null>(null);

  const runIndex = () => {
    setLibError(null);
    startLibraryIndex().then(() => refresh()).catch((e) => setLibError(String(e.message ?? e)));
  };

  const busy = libJob?.status === "running";

  return (
    <div className="space-y-3 text-sm">
      <div>
        <div className="text-sm font-semibold uppercase tracking-wide text-fg-strong">{t.settings.canonicalLibraryTitle}</div>
        <p className="mt-1 text-sm text-muted">{t.settings.canonicalLibraryBody}</p>
      </div>
      {libError && <Alert tone="danger">⚠ {libError}</Alert>}
      {libJob?.status === "error" && <Alert tone="danger">⚠ {libJob.error ?? t.settings.indexFailedFallback}</Alert>}
      <Button size="sm" onClick={runIndex} disabled={busy}>{busy ? t.settings.indexingLabel : t.settings.indexNowButton}</Button>
      {busy && (
        <p className="tnum text-sm text-muted">{t.settings.indexingProgress(libJob.processed, libJob.total)}</p>
      )}
      {libJob?.status === "done" && libJob.result?.linking && (
        <p className="text-sm text-fg">
          {t.settings.indexResultSummary(
            libJob.result.linking.scanned, libJob.result.linking.matched, libJob.result.linking.created,
            libJob.result.linking.duplicates, libJob.result.linking.relinked, libJob.result.linking.lost,
            libJob.result.linking.failed,
          )}
        </p>
      )}
    </div>
  );
}
