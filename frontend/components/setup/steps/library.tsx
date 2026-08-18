"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  errText, getConfigSettings, libraryIndexStatus, pickerAvailability, startLibraryIndex,
  type ConfigSettings, type LibraryIndexJob,
} from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { PathField } from "../path-field";

export function LibraryStep() {
  const t = useT();
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [canPick, setCanPick] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getConfigSettings().then(setConfig).catch((e) => setError(errText(e)));
  }, []);

  useEffect(() => {
    load();
    pickerAvailability().then((r) => setCanPick(r.available)).catch(() => setCanPick(false));
  }, [load]);

  if (!config) return error ? <Alert tone="danger">{error}</Alert> : <Loading />;

  return (
    <div className="space-y-4">
      <p className="text-sm leading-relaxed text-muted">{t.setup.libraryBody}</p>
      {error && <Alert tone="danger">{error}</Alert>}
      <PathField
        fieldKey="library_root"
        label={t.setup.libraryRootLabel}
        value={config.library_root.value}
        detail={config.library_root.detail}
        canPick={canPick}
        onSaved={setConfig}
      />
      <PathField
        fieldKey="archive_root"
        label={t.setup.archiveRootLabel}
        value={config.archive_root.value}
        detail={config.archive_root.detail}
        canPick={canPick}
        onSaved={setConfig}
      />
      <IndexAction disabled={!config.library_root.value} />
    </div>
  );
}

function IndexAction({ disabled }: { disabled: boolean }) {
  const t = useT();
  const [job, setJob] = useState<LibraryIndexJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  const avvia = async () => {
    setError(null);
    try {
      setJob(await startLibraryIndex());
    } catch (e) {
      setError(errText(e));
      return;
    }
    timer.current = setInterval(async () => {
      const st = await libraryIndexStatus();
      setJob(st);
      if (st.status !== "running" && timer.current) clearInterval(timer.current);
    }, 1000);
  };

  const running = job?.status === "running";
  return (
    <div className="space-y-2">
      <Button size="sm" variant="outline" disabled={disabled || running} onClick={avvia}>
        {running ? t.setup.indexing : t.setup.indexNow}
      </Button>
      {running && (
        <p className="tnum text-xs text-muted">{job.processed} / {job.total}</p>
      )}
      {job?.status === "done" && (
        <p className="text-xs text-fg-strong">{t.setup.indexDone(job.processed)}</p>
      )}
      {job?.status === "error" && <p className="text-xs text-danger">{job.error}</p>}
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}
