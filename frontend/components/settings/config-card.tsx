"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  errText, getConfigSettings, patchConfigSettings, setDownloadSlots, setLibraryShare, startLibraryIndex,
  type ConfigPatch, type ConfigSettings,
} from "@/lib/api";
import { Alert, Badge, Button, Checkbox, Field, Input, Loading, Spinner } from "@/components/ui";
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

export function ConfigCard({ section = "library" }: { section?: "library" | "downloads" }) {
  const t = useT();
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [savedFields, setSavedFields] = useState<readonly ConfigFieldKey[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [shareBusy, setShareBusy] = useState(false);
  const [shareMsg, setShareMsg] = useState<string | null>(null);
  const pickerOk = usePickerAvailability();

  const hydrate = useCallback((c: ConfigSettings) => {
    setConfig(c);
    setError(null);
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

  const save = async (fields: readonly ConfigFieldKey[]) => {
    if (!config) return;
    const patch: ConfigPatch = {};
    for (const k of fields) if (draft[k] !== config[k].value) patch[k] = draft[k];
    setSaving(true); setError(null); setSavedFields([]);
    try {
      const updated = await patchConfigSettings(patch);
      setConfig(updated);
      setWarning(updated.warning);
      // Salvare in una sezione non deve buttare la bozza dell'altra.
      setDraft((current) => Object.fromEntries(CONFIG_FIELDS.map((k) => [
        k, k in patch || current[k] === config[k].value ? updated[k].value : current[k],
      ])));
      setSavedFields(fields);
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
        {error ? <><Alert tone="danger">{error}</Alert><Button size="sm" variant="outline" className="mt-3" onClick={reloadConfig}>{t.settings.retryButton}</Button></> : <Loading />}
      </div>
    );
  }

  const libraryFields = ["library_root", "archive_root"] as const;
  const downloadFields = ["slskd_download_dir", "slskd_url", "slskd_config_path"] as const;
  const dirty = (fields: readonly ConfigFieldKey[]) => fields.some((k) => draft[k] !== config[k].value);
  const field = (k: ConfigFieldKey) => {
    const f = config[k];
    const unchanged = draft[k] === f.value;
    const pickKind = PICK_KIND[k];
    return (
      <Field key={k} label={<span className="flex flex-wrap items-center gap-2">
        {FIELD_LABEL[k]}
        {f.source === "db" && <Badge tone="info">{t.settings.overrideBadge}</Badge>}
        {unchanged && !f.valid && <Badge tone="danger">{f.detail}</Badge>}
      </span>} hint={!unchanged ? t.settings.unsavedHint
        // Una nota su un valore valido («cartella non scrivibile», «Disattivato
        // (vuoto)») è dell'utente quanto un errore: resta l'hint del campo.
        : f.valid && f.detail ? f.detail
        : k === "slskd_download_dir" ? t.settings.downloadFolderHint : undefined}>
        <fieldset disabled={saving} className="flex min-w-0 flex-wrap items-center gap-2">
          <Input className="min-w-0 flex-1" value={draft[k] ?? ""} disabled={saving}
            onChange={(e) => { setSavedFields([]); setDraft((d) => ({ ...d, [k]: e.target.value })); }} />
          {pickerOk && pickKind && <PathPickerButton kind={pickKind} start={draft[k]} prompt={FIELD_LABEL[k]}
            onPick={(p) => { setSavedFields([]); setDraft((d) => ({ ...d, [k]: p })); }} onError={setError} />}
        </fieldset>
      </Field>
    );
  };
  const saveButton = (fields: readonly ConfigFieldKey[]) => (
    <div className="flex flex-wrap items-center gap-3">
      <Button type="submit" size="sm" disabled={saving || !dirty(fields)}>
        {saving && <Spinner />} {t.settings.saveButton}
      </Button>
      {savedFields.length > 0 && fields.every((k) => savedFields.includes(k)) && !dirty(fields) && <span role="status" className="text-xs text-muted">{t.settings.savedLabel}</span>}
    </div>
  );

  return (
    <div>
      {error && <div className="mb-4"><Alert tone="danger">{error}</Alert></div>}
      {warning && <div className="mb-4"><Alert tone="warning">{warning}</Alert></div>}
      <section hidden={section !== "library"} aria-label={t.settings.sections.library} className="space-y-6">
        <p className="text-sm text-muted">{t.settings.libraryHint}</p>
        <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); if (dirty(libraryFields) && !saving) void save(libraryFields); }}>
          {libraryFields.map(field)}
          {saveButton(libraryFields)}
        </form>
        <div className="border-t border-border pt-5"><LibraryIndexSection /></div>
      </section>
      <section hidden={section !== "downloads"} aria-label={t.settings.sections.downloads} className="space-y-6">
        <p className="text-sm text-muted">{t.settings.downloadsHint}</p>
        <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); if (dirty(downloadFields) && !saving) void save(downloadFields); }}>
          {field("slskd_download_dir")}
          <details className="border-t border-border pt-4">
            <summary className="cursor-pointer text-sm text-muted">{t.settings.advancedSoulseek}</summary>
            <div className="mt-5 space-y-5">{field("slskd_url")}{field("slskd_config_path")}</div>
          </details>
          {saveButton(downloadFields)}
        </form>
        <div className="border-t border-border">
          <DownloadSlotsSection value={config.download_slots} onSaved={(download_slots) => setConfig((c) => c ? { ...c, download_slots } : c)} />
        </div>
        <div className="border-t border-border pt-5">
          <Checkbox label={t.settings.shareLibraryLabel} checked={config.share_library} disabled={shareBusy} onChange={toggleShare} />
          <p className="mt-1.5 text-xs text-muted">{t.settings.shareLibraryHint}</p>
          {shareMsg && <p role="status" className="mt-1.5 text-xs text-fg">{shareMsg}</p>}
        </div>
      </section>
    </div>
  );
}

/** Quanti download Soulseek in parallelo (B-Task 6: la coda ha un pool di N
 *  slot). Salva su blur, non a ogni tasto; un valore invariato non fa
 *  scrivere nulla, un valore fuori scala 1-10 non fa scrivere nulla (il
 *  backend risponderebbe 422) e riporta il campo al valore in vigore
 *  invece di restare bloccato su quello invalido. Si riallinea anche se
 *  `value` cambia da fuori (reload di altri campi), tranne mentre l'utente
 *  ci sta digitando dentro. */
function DownloadSlotsSection({ value, onSaved }: { value: number; onSaved: (value: number) => void }) {
  const t = useT();
  const [slots, setSlots] = useState(value);
  const [error, setError] = useState<string | null>(null);
  // true mentre l'utente ha il focus sul campo: il riallineamento dal
  // valore esterno (rilievo minor) deve saltare in quella finestra, per
  // non cancellare quello che sta digitando.
  const editingRef = useRef(false);

  useEffect(() => {
    if (!editingRef.current) setSlots(value);
  }, [value]);

  const save = async () => {
    if (slots === value) return;
    if (!Number.isInteger(slots) || slots < 1 || slots > 10) {
      // Scrittura scartata (il backend risponderebbe 422): il campo non
      // deve restare bloccato sul valore invalido, torna a quello in
      // vigore (rilievo important).
      setSlots(value);
      setError(t.settings.downloadSlotsInvalid);
      return;
    }
    try {
      const result = await setDownloadSlots(slots);
      setError(null);
      onSaved(result.download_slots);
    } catch (e) { setError(errText(e)); }
  };

  return (
    <div>
      {error && <div className="px-5 pt-3"><Alert tone="danger">⚠ {error}</Alert></div>}
      <label className="flex items-center gap-3 py-4 text-sm">
        <span className="flex-1">
          {t.settings.downloadSlotsLabel}
          <span className="mt-0.5 block text-xs text-muted">{t.settings.downloadSlotsHint}</span>
        </span>
        <Input type="number" min={1} max={10} className="h-8 w-20"
          value={slots}
          onChange={(e) => setSlots(Number(e.target.value))}
          onFocus={() => { editingRef.current = true; }}
          onBlur={() => { editingRef.current = false; void save(); }} />
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
