"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, ExternalLink, Plug, Unplug } from "lucide-react";
import {
  daemonStart, daemonStatus, daemonStop, errText,
  getConfigSettings, setSoundcloudUsername, slskdConnect, slskdDisconnect, slskdStatus,
  soundcloudStatus, SPOTIFY_LOGIN_URL,
  type ConfigSettings, type ServiceStatus, type SlskdDaemonStatus, type SlskdStatus,
  type SoundCloudStatus, type SpotifyStatus,
} from "@/lib/api";
import { runFingerprint, type FingerprintResult } from "@/lib/organize/api";
import { Alert, Button, Input, Spinner } from "@/components/ui";
import { useT, type Dictionary } from "@/lib/i18n";
import { ServiceCard } from "@/components/setup/service-card";
import { PathField } from "@/components/setup/path-field";
import { SERVICE_FIELDS, type ServiceKey } from "@/lib/setup-services";

/* La lista unificata dei servizi esterni: una riga per servizio, semantica di
   stato unica, azioni inline dove servono (OAuth Spotify, login slskd,
   username SoundCloud, fingerprint AcoustID). Sostituisce la vecchia coppia
   lista Servizi + ProviderList di Organize e le card SoulseekCard e
   SoundCloudCard (fusione F1-F6: un prodotto, una lista). */

function statusLabel(s: ServiceStatus, t: Dictionary): { text: string; strong: boolean } {
  if (s.connected === true) return { text: t.settings.statusConnected, strong: true };
  if (s.connected === false) return { text: t.settings.statusToConnect, strong: false };
  if (s.configured && s.optional_ok === false) return { text: t.settings.statusOptionalToken, strong: true };
  if (s.configured) return { text: t.settings.statusActive, strong: true };
  return { text: t.settings.statusNotConfigured, strong: false };
}

export function ServicesList({ services, spotify, onServicesChanged }: {
  services: ServiceStatus[];
  spotify: SpotifyStatus | null;
  /* Ricarica lo stato dei servizi del genitore (badge di riga): senza,
     dopo un salvataggio da riga espansa il pannello passa a "configurato"
     ma il badge sopra resta indietro finché non si ricarica la pagina.
     Opzionale per non rompere i chiamanti/test esistenti che non lo passano. */
  onServicesChanged?: () => void;
}) {
  const t = useT();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [config, setConfig] = useState<ConfigSettings | null>(null);
  const loadConfig = useCallback(() => {
    getConfigSettings().then(setConfig).catch(() => setConfig(null));
  }, []);
  useEffect(loadConfig, [loadConfig]);
  const handleSaved = useCallback(() => {
    loadConfig();
    onServicesChanged?.();
  }, [loadConfig, onServicesChanged]);
  return (
    <div className="border border-border">
      {services.map((s, i) => (
        <div key={s.key} className="border-b border-border p-5 last:border-0">
          <div className="flex items-start justify-between gap-4">
            <div className="flex min-w-0 gap-3">
              <span className="tnum mt-0.5 text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
              <div className="min-w-0">
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="text-sm font-semibold uppercase tracking-wide text-fg-strong">{s.name}</span>
                  <span className="text-[10px] uppercase tracking-wider text-faint">{t.settings.servicesMeta[s.key]?.category ?? s.category}</span>
                </div>
                <p className="mt-1 text-sm text-muted">{t.settings.servicesMeta[s.key]?.detail ?? s.detail}</p>
                <p className="mt-1.5 flex flex-wrap items-center gap-1.5 text-xs text-faint">
                  {s.env.map((e) => <code key={e} className="rounded-none bg-elevated px-1">{e}</code>)}
                  {s.optional_env.map((e) => (
                    <code key={e} className="rounded-none bg-elevated px-1 opacity-70">
                      {e} <span className="text-[9px] uppercase">{t.settings.optionalBadge}</span>
                    </code>
                  ))}
                  <a href={s.docs} target="_blank" rel="noreferrer" className="text-fg underline-offset-4 hover:underline">docs ↗</a>
                </p>
              </div>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-2">
              {s.key !== "slskd" && (() => {
                const st = statusLabel(s, t);
                return <span className={`text-[10px] uppercase tracking-wider ${st.strong ? "text-fg-strong" : "text-muted"}`}>{st.text}</span>;
              })()}
              {s.key === "spotify" && (
                <a href={SPOTIFY_LOGIN_URL}>
                  <Button size="sm" variant="outline"><ExternalLink size={14} /> {s.connected ? t.settings.reconnectButton : t.settings.connectButton}</Button>
                </a>
              )}
              {SERVICE_FIELDS[s.key as ServiceKey] && (
                <Button size="sm" variant="ghost"
                        onClick={() => setExpanded(expanded === s.key ? null : s.key)}>
                  {expanded === s.key ? t.settings.collapseKeys : t.settings.editKeys}
                </Button>
              )}
            </div>
          </div>
          {s.key === "spotify" && <SpotifyExtra s={s} spotify={spotify} t={t} />}
          {s.key === "slskd" && <SlskdExtra t={t} />}
          {s.key === "soundcloud" && <SoundCloudExtra t={t} />}
          {s.key === "acoustid" && s.configured && <AcoustidExtra t={t} />}
          {expanded === s.key && config && (
            <div className="mt-4 border-t border-border pt-4">
              <ServiceCard
                service={s.key as ServiceKey}
                secrets={config.secrets}
                redirectUri={config.spotify_redirect_uri}
                docsUrl={s.docs}
                onSaved={handleSaved}
              >
                {/* ai_model non è un segreto: stesso PathField dei percorsi,
                    per non avere un editor diverso fra wizard e Impostazioni. */}
                {s.key === "anthropic" && (
                  <PathField
                    fieldKey="ai_model"
                    label={t.setup.aiModelLabel}
                    value={config.ai_model.value}
                    detail={config.ai_model.detail ?? t.setup.aiModelHint}
                    canPick={false}
                    kind="text"
                    onSaved={setConfig}
                  />
                )}
              </ServiceCard>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function SpotifyExtra({ s, spotify, t }: { s: ServiceStatus; spotify: SpotifyStatus | null; t: Dictionary }) {
  const [copied, setCopied] = useState(false);
  if (!spotify?.configured) return null;
  const copyRedirect = async () => {
    await navigator.clipboard.writeText(spotify.redirect_uri);
    setCopied(true); setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div className="mt-3 border border-border bg-bg p-3">
      <p className="mb-1.5 text-xs text-muted">{t.settings.redirectUriPrefix} <strong>{t.settings.redirectUriExactTerm}</strong> {t.settings.redirectUriSuffix}</p>
      <div className="flex items-center gap-2">
        <code className="flex-1 break-all bg-elevated px-2 py-1 text-xs text-fg">{spotify.redirect_uri}</code>
        <Button size="sm" variant="outline" onClick={copyRedirect}>{copied ? <><Check size={14} /> {t.settings.copiedLabel}</> : <><Copy size={14} /> {t.settings.copyButton}</>}</Button>
      </div>
      {s.connected && (
        <p className="mt-2 text-xs text-muted">
          {t.settings.reauthorizeHintPrefix} <code className="rounded-none bg-elevated px-1">403</code>, {t.settings.reauthorizeHintMiddle} <strong>{t.settings.reconnectButton}</strong> {t.settings.reauthorizeHintSuffix}
        </p>
      )}
    </div>
  );
}

function SlskdExtra({ t }: { t: Dictionary }) {
  const [status, setStatus] = useState<SlskdStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    slskdStatus()
      .then((s) => { setStatus(s); setError(null); })
      .catch((e) => setError(String((e as Error).message ?? e)));
  }, []);
  useEffect(load, [load]);

  // Stato/comandi del demone stesso (accendi/spegni il processo), separati
  // dallo stato di login soulseek sopra: qui non si riconfigura né si
  // riscarica, a differenza del passo del wizard — a regime le credenziali
  // ci sono già e il binario pure (se manca, il backend risponde 409
  // slskd_not_installed e il messaggio tradotto rimanda al wizard).
  const [daemon, setDaemon] = useState<SlskdDaemonStatus | null>(null);
  const [inCorso, setInCorso] = useState(false);
  const [erroreDemone, setErroreDemone] = useState<string | null>(null);

  useEffect(() => { daemonStatus().then(setDaemon).catch(() => setDaemon(null)); }, []);

  const comanda = async (azione: () => Promise<SlskdDaemonStatus>) => {
    setInCorso(true);
    setErroreDemone(null);
    try {
      setDaemon(await azione());
    } catch (e) {
      setErroreDemone(errText(e));
    } finally {
      setInCorso(false);
    }
  };

  // Stesse tre possibilità del wizard: true = l'abbiamo avviato noi, false =
  // acceso ma da qualcun altro, null = non rilevabile su questa piattaforma
  // (niente tool di processo, es. Windows) — non va spacciato per "non
  // nostro".
  const daemonLabel = daemon?.reachable
    ? (daemon.owned === true
        ? t.setup.daemonRunning
        : daemon.owned === false
        ? t.setup.daemonRunningElsewhere
        : t.setup.daemonRunningUnknownOwner)
    : t.setup.daemonStopped;

  // Dopo connect/disconnect slskd resta "in transizione" per qualche secondo
  // (Connecting → LoggingIn → LoggedIn): polling breve e limitato finche' lo
  // stato si stabilizza, pulsanti disabilitati nel frattempo.
  const act = async (fn: () => Promise<SlskdStatus>) => {
    setBusy(true); setError(null);
    try {
      let s = await fn();
      setStatus(s);
      for (let i = 0; i < 10 && (s.is_transitioning || s.is_connecting); i++) {
        await new Promise((r) => setTimeout(r, 1000));
        s = await slskdStatus();
        setStatus(s);
      }
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
  };

  const st = ((): { text: string; strong: boolean } => {
    if (!status) return { text: "—", strong: false };
    if (!status.configured) return { text: t.settings.soulseekNotConfigured, strong: false };
    if (!status.reachable) return { text: t.settings.soulseekUnreachable, strong: false };
    if (status.is_connecting || status.is_transitioning) return { text: t.settings.soulseekConnecting, strong: false };
    if (status.is_connected && status.is_logged_in) {
      return { text: status.username ? t.settings.soulseekConnectedAs(status.username) : t.settings.soulseekConnected, strong: true };
    }
    return { text: t.settings.soulseekDisconnected, strong: false };
  })();

  const canAct = !!status?.configured && !!status?.reachable;
  const connected = !!status?.is_connected && !!status?.is_logged_in;

  return (
    <div className="mt-3 border border-border bg-bg p-3">
      <div className="flex items-center justify-between gap-4">
        <span className={`text-sm ${st.strong ? "text-fg-strong" : "text-muted"}`}>{st.text}</span>
        {canAct && (
          connected ? (
            <Button size="sm" variant="outline" onClick={() => act(slskdDisconnect)} disabled={busy}>
              {busy ? <Spinner /> : <Unplug size={14} />} {t.settings.soulseekDisconnect}
            </Button>
          ) : (
            <Button size="sm" onClick={() => act(slskdConnect)} disabled={busy}>
              {busy ? <Spinner /> : <Plug size={14} />} {t.settings.soulseekConnect}
            </Button>
          )
        )}
      </div>
      {error && <Alert tone="danger">⚠ {error}</Alert>}
      {daemon && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-muted">{daemonLabel}</span>
          {daemon.reachable && daemon.owned === true && (
            <Button size="sm" variant="outline" disabled={inCorso}
                    onClick={() => comanda(daemonStop)}>
              {t.setup.daemonStop}
            </Button>
          )}
          {!daemon.reachable && (
            <Button size="sm" variant="outline" disabled={inCorso}
                    onClick={() => comanda(daemonStart)}>
              {t.setup.daemonStart}
            </Button>
          )}
          {erroreDemone && <span className="text-xs text-danger">{erroreDemone}</span>}
        </div>
      )}
    </div>
  );
}

function SoundCloudExtra({ t }: { t: Dictionary }) {
  const [status, setStatus] = useState<SoundCloudStatus | null>(null);
  const [username, setUsername] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    soundcloudStatus()
      .then((s) => { setStatus(s); setUsername(s.username ?? ""); })
      .catch(() => setStatus(null));
  }, []);

  const save = async () => {
    setError(null); setSaving(true);
    try { setStatus(await setSoundcloudUsername(username.trim())); }
    catch (e) { setError(String((e as { message?: string })?.message ?? e)); }
    finally { setSaving(false); }
  };

  return (
    <div className="mt-3 grid gap-2 border border-border bg-bg p-3">
      {status && !status.available && <Alert tone="warning">{t.settings.soundcloudYtdlpUnavailable}</Alert>}
      {error && <Alert tone="danger">⚠ {error}</Alert>}
      <div className="flex items-center gap-2">
        <span className="shrink-0 text-xs text-muted">{t.settings.usernameLabel}</span>
        <Input className="flex-1" value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder={t.settings.usernamePlaceholder} disabled={saving} />
        <Button size="sm" onClick={save} disabled={saving || username.trim() === ""}>
          {saving ? <Spinner /> : t.common.save}
        </Button>
      </div>
      {status?.ytdlp_version && <p className="text-xs text-faint">yt-dlp {status.ytdlp_version}</p>}
    </div>
  );
}

function AcoustidExtra({ t }: { t: Dictionary }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<FingerprintResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const identify = async () => {
    setError(null); setBusy(true);
    try { setResult(await runFingerprint()); }
    catch (e) { setError(String((e as { message?: string })?.message ?? e)); }
    finally { setBusy(false); }
  };

  return (
    <div className="mt-3 flex flex-wrap items-center gap-3 border border-border bg-bg p-3">
      <Button size="sm" variant="outline" onClick={identify} disabled={busy}>
        {busy ? <><Spinner /> {t.settings.identifyBusy}</> : t.settings.identifyNow}
      </Button>
      {result && (
        <span className="text-xs text-muted">
          {t.settings.fpResult(result.identified, result.below_threshold, result.not_found, result.errors, result.total)}
        </span>
      )}
      {error && <Alert tone="danger">⚠ {error}</Alert>}
    </div>
  );
}
