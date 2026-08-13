"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, Copy, ExternalLink, Plug, Unplug } from "lucide-react";
import {
  setSoundcloudUsername, slskdConnect, slskdDisconnect, slskdStatus,
  soundcloudStatus, SPOTIFY_LOGIN_URL,
  type ServiceStatus, type SlskdStatus, type SoundCloudStatus, type SpotifyStatus,
} from "@/lib/api";
import { runFingerprint, type FingerprintResult } from "@/lib/organize/api";
import { Alert, Button, Input, Spinner } from "@/components/ui";
import { useT, type Dictionary } from "@/lib/i18n";

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

export function ServicesList({ services, spotify }: {
  services: ServiceStatus[];
  spotify: SpotifyStatus | null;
}) {
  const t = useT();
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
                  <span className="text-[10px] uppercase tracking-wider text-faint">{s.category}</span>
                </div>
                <p className="mt-1 text-sm text-muted">{s.detail}</p>
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
            </div>
          </div>
          {s.key === "spotify" && <SpotifyExtra s={s} spotify={spotify} t={t} />}
          {s.key === "slskd" && <SlskdExtra t={t} />}
          {s.key === "soundcloud" && <SoundCloudExtra t={t} />}
          {s.key === "acoustid" && s.configured && <AcoustidExtra t={t} />}
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
    <div className="mt-3 flex items-center justify-between gap-4 border border-border bg-bg p-3">
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
      {error && <Alert tone="danger">⚠ {error}</Alert>}
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
