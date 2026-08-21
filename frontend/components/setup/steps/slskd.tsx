"use client";

import { useCallback, useEffect, useState } from "react";
import {
  daemonConfig, daemonStart, daemonStatus, daemonStop,
  errText, getConfigSettings, getInstallStatus, pickerAvailability, slskdStatus, startInstall,
  type ConfigSettings, type SlskdDaemonStatus, type SlskdStatus,
} from "@/lib/api";
import { Alert, Button, Field, Input, Loading } from "@/components/ui";
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

  const [daemon, setDaemon] = useState<SlskdDaemonStatus | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [avvio, setAvvio] = useState(false);
  const [erroreDemone, setErroreDemone] = useState<string | null>(null);

  const load = useCallback(() => {
    getConfigSettings()
      .then((config) => {
        setError(null);
        setConfig(config);
      })
      .catch((e) => setError(errText(e)));
  }, []);

  useEffect(() => {
    load();
    pickerAvailability().then((r) => setCanPick(r.available)).catch(() => setCanPick(false));
    daemonStatus().then(setDaemon).catch(() => setDaemon(null));
  }, [load]);

  const verifica = async () => {
    setError(null);
    try {
      setStatus(await slskdStatus());
    } catch (e) {
      setError(errText(e));
    }
  };

  // Scarica il binario, scrive le credenziali nel file di configurazione di
  // slskd e lo avvia: qui, nel wizard, il demone non c'è ancora (in
  // Impostazioni, a regime, basta avviarlo — vedi SlskdExtra).
  const scaricaEAvvia = async () => {
    setAvvio(true);
    setErroreDemone(null);
    try {
      await daemonConfig({ username, password });
      setPassword(""); // non resta in memoria oltre l'invio
      await startInstall("slskd");
      while ((await getInstallStatus()).status === "running") {
        await new Promise((r) => setTimeout(r, 1000));
      }
      setDaemon(await daemonStart());
    } catch (e) {
      setErroreDemone(errText(e));
    } finally {
      setAvvio(false);
    }
  };

  if (!config) return error ? <Alert tone="danger">{error}</Alert> : <Loading />;

  // owned: true = l'abbiamo avviato noi; false = acceso ma da qualcun altro;
  // null = la piattaforma non sa dircelo (mancano i tool di processo, es.
  // Windows). Il bottone Ferma compare solo per true: null non va presentato
  // come "non nostro", l'utente non può farci nulla in nessuno dei due casi
  // ma dirgli la cosa sbagliata è peggio che non dirgli niente.
  const daemonLabel = daemon?.owned === true
    ? t.setup.daemonRunning
    : daemon?.owned === false
    ? t.setup.daemonRunningElsewhere
    : t.setup.daemonRunningUnknownOwner;

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

      <div className="border-t border-border pt-4">
        <p className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted">{t.setup.daemonTitle}</p>
        {daemon?.reachable ? (
          // Qualcosa risponde già all'URL configurato: non offriamo di
          // avviare nulla, è il caso normale (l'utente spesso ha già slskd
          // suo).
          <div className="flex items-center gap-3">
            <span className="text-xs text-fg-strong">{daemonLabel}</span>
            {daemon.owned === true && (
              <Button size="sm" variant="outline"
                      onClick={async () => setDaemon(await daemonStop())}>
                {t.setup.daemonStop}
              </Button>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            <Field label={t.setup.daemonUsername}>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} />
            </Field>
            <Field label={t.setup.daemonPassword}>
              <Input type="password" value={password}
                     onChange={(e) => setPassword(e.target.value)} />
            </Field>
            <p className="text-xs text-faint">{t.setup.daemonCredentialsNote}</p>
            <Button size="sm" variant="outline" disabled={avvio || !username || !password}
                    onClick={scaricaEAvvia}>
              {avvio ? t.setup.daemonStarting : t.setup.daemonInstallAndStart}
            </Button>
            {erroreDemone && <Alert tone="danger">{erroreDemone}</Alert>}
          </div>
        )}
      </div>
    </div>
  );
}
