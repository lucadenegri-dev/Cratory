"use client";

import { useCallback, useEffect, useState } from "react";
import {
  errText, getConfigSettings, pickerAvailability, slskdStatus,
  type ConfigSettings, type SlskdStatus,
} from "@/lib/api";
import { Alert, Button, Loading } from "@/components/ui";
import { useT } from "@/lib/i18n";
import { ServiceGuide } from "../service-guide";
import { CredentialField } from "../credential-field";
import { PathField } from "../path-field";

export function SlskdStep() {
  const t = useT();
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const [status, setStatus] = useState<SlskdStatus | null>(null);
  const [canPick, setCanPick] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getConfigSettings().then(setConfig).catch((e) => setError(errText(e)));
  }, []);

  useEffect(() => {
    load();
    pickerAvailability().then((r) => setCanPick(r.available)).catch(() => setCanPick(false));
  }, [load]);

  const verifica = async () => {
    try {
      setStatus(await slskdStatus());
    } catch (e) {
      setError(errText(e));
    }
  };

  if (!config) return error ? <Alert tone="danger">{error}</Alert> : <Loading />;

  return (
    <div className="space-y-4">
      <ServiceGuide service="slskd" docsUrl="https://github.com/slskd/slskd" copyValue={null} />
      {error && <Alert tone="danger">{error}</Alert>}

      <PathField
        fieldKey="slskd_url"
        label={t.setup.slskdUrlLabel}
        value={config.slskd_url.value}
        detail={config.slskd_url.detail}
        canPick={false}
        kind="text"
        onSaved={setConfig}
      />

      <PathField
        fieldKey="slskd_download_dir"
        label={t.setup.slskdDownloadDirLabel}
        value={config.slskd_download_dir.value}
        detail={config.slskd_download_dir.detail}
        canPick={canPick}
        onSaved={setConfig}
      />

      <CredentialField
        fieldKey="slskd_api_key"
        label={t.setup.fieldLabels.slskd_api_key}
        state={config.secrets.slskd_api_key}
        onSaved={load}
      />

      <div className="flex flex-wrap items-center gap-3">
        <Button size="sm" variant="outline" onClick={verifica}>{t.setup.slskdCheck}</Button>
        {status && (
          <span className={`text-xs ${status.reachable ? "text-fg-strong" : "text-danger"}`}>
            {status.reachable ? t.setup.slskdReachable : t.setup.slskdUnreachable}
          </span>
        )}
      </div>
    </div>
  );
}
