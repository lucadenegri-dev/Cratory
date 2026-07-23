"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Copy, Check, ExternalLink, Plug, Unplug } from "lucide-react";
import {
  apiGet, servicesStatus, setSoundcloudUsername, slskdConnect, slskdDisconnect, slskdStatus,
  soundcloudStatus, SPOTIFY_LOGIN_URL, startLibraryIndex,
  type ServiceStatus, type SlskdStatus, type SoundCloudStatus, type SpotifyStatus,
} from "@/lib/api";
import { Alert, Button, Card, CardHeader, Field, Input, Loading, Spinner } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { useI18n, useT, type Dictionary } from "@/lib/i18n";
import { cn } from "@/lib/cn";

function statusLabel(s: ServiceStatus, t: Dictionary): { text: string; strong: boolean } {
  if (s.connected === true) return { text: t.settings.statusConnected, strong: true };
  if (s.connected === false) return { text: t.settings.statusToConnect, strong: false };
  if (s.configured) return { text: t.settings.statusConfigured, strong: true };
  return { text: t.settings.statusNotConfigured, strong: false };
}

function SettingsInner() {
  const { lang, setLang, t } = useI18n();
  const params = useSearchParams();
  const oauth = params.get("spotify");
  const [services, setServices] = useState<ServiceStatus[] | null>(null);
  const [spotify, setSpotify] = useState<SpotifyStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    servicesStatus().then((r) => { setServices(r.services); setError(null); }).catch((e) => { setServices(null); setError(String(e.message ?? e)); });
    apiGet<SpotifyStatus>("/api/spotify/status").then(setSpotify).catch(() => setSpotify(null));
  }, []);
  useEffect(load, [load]);

  async function copyRedirect() {
    if (!spotify?.redirect_uri) return;
    await navigator.clipboard.writeText(spotify.redirect_uri);
    setCopied(true); setTimeout(() => setCopied(false), 1500);
  }

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>{t.settings.marginaliaPrefix} <code className="rounded-none bg-elevated px-1">backend/.env</code> {t.settings.marginaliaSuffix}</p>
    </div>
  );

  return (
    <PageLayout title={t.settings.pageTitle} marginaliaTitle={t.settings.helpTitle} marginalia={marginalia}>
      {oauth === "connected" && <div className="mb-4"><Alert tone="info">{t.settings.spotifyConnected}</Alert></div>}
      {oauth === "error" && <div className="mb-4"><Alert tone="danger">{t.settings.spotifyLoginFailed(params.get("detail") ?? "")}</Alert></div>}
      {error && <div className="mb-4"><Alert tone="danger">{t.dashboard.backendDown(error)}</Alert></div>}

      <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.settings.languageLabel}</div>
      <div className="border border-border p-5">
        <div role="group" aria-label={t.settings.languageLabel} className="inline-flex rounded-none border border-border bg-surface p-1">
          <button
            type="button"
            aria-pressed={lang === "it"}
            onClick={() => setLang("it")}
            className={cn("rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
              lang === "it" ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
          >
            {t.settings.languageIt}
          </button>
          <button
            type="button"
            aria-pressed={lang === "en"}
            onClick={() => setLang("en")}
            className={cn("rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
              lang === "en" ? "bg-elevated text-fg" : "text-muted hover:text-fg")}
          >
            {t.settings.languageEn}
          </button>
        </div>
      </div>

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">{t.settings.servicesHeading}</div>
      <div className="border border-border">
        {services?.map((s, i) => {
          const st = statusLabel(s, t);
          return (
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
                      <a href={s.docs} target="_blank" rel="noreferrer" className="text-fg underline-offset-4 hover:underline">docs ↗</a>
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 flex-col items-end gap-2">
                  <span className={`text-[10px] uppercase tracking-wider ${st.strong ? "text-fg-strong" : "text-muted"}`}>{st.text}</span>
                  {s.key === "spotify" && (
                    <a href={SPOTIFY_LOGIN_URL}>
                      <Button size="sm" variant="outline"><ExternalLink size={14} /> {s.connected ? t.settings.reconnectButton : t.settings.connectButton}</Button>
                    </a>
                  )}
                </div>
              </div>

              {s.key === "spotify" && spotify?.configured && (
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
              )}
            </div>
          );
        })}
        {!services && !error && <div className="px-5"><Loading /></div>}
      </div>

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">{t.settings.libraryHeading}</div>
      <LibraryIndexCard />

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">SoundCloud</div>
      <SoundCloudCard />

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">Soulseek</div>
      <SoulseekCard />
    </PageLayout>
  );
}

function SoulseekCard() {
  const t = useT();
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
  // (Connecting → LoggingIn → LoggedIn): si fa polling breve e limitato finché
  // lo stato si stabilizza, tenendo i pulsanti disabilitati nel frattempo.
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
    <Card>
      <CardHeader title="Soulseek" subtitle={t.settings.soulseekSubtitle} />
      <div className="flex items-center justify-between gap-4 p-4">
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
      {error && <div className="px-4 pb-4"><Alert tone="danger">⚠ {error}</Alert></div>}
    </Card>
  );
}

function SoundCloudCard() {
  const t = useT();
  const [status, setStatus] = useState<SoundCloudStatus | null>(null);
  const [username, setUsername] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    soundcloudStatus()
      .then((s) => {
        setStatus(s);
        setUsername(s.username ?? "");
      })
      .catch(() => setStatus(null));
  }, []);

  const save = async () => {
    setError(null);
    setSaving(true);
    try {
      setStatus(await setSoundcloudUsername(username.trim()));
    } catch (e) {
      setError(String((e as { message?: string })?.message ?? e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader
        title="SoundCloud"
        subtitle={t.settings.soundcloudSubtitle}
      />
      <div className="grid gap-3 p-4">
        {status && !status.available && (
          <Alert tone="warning">{t.settings.soundcloudYtdlpUnavailable}</Alert>
        )}
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        <Field label={t.settings.usernameLabel}>
          <div className="flex items-center gap-2">
            <Input
              className="flex-1"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder={t.settings.usernamePlaceholder}
              disabled={saving}
            />
            <Button size="sm" onClick={save} disabled={saving || username.trim() === ""}>
              {saving ? <Spinner /> : t.common.save}
            </Button>
          </div>
        </Field>
        {status?.ytdlp_version && (
          <p className="text-xs text-faint">yt-dlp {status.ytdlp_version}</p>
        )}
      </div>
    </Card>
  );
}

function LibraryIndexCard() {
  const t = useT();
  // Lo stato arriva dal poller globale (JobsProvider): niente polling qui.
  const { libraryIndex: libJob, refresh } = useJobs();
  const [libError, setLibError] = useState<string | null>(null);

  const runIndex = () => {
    setLibError(null);
    startLibraryIndex().then(() => refresh()).catch((e) => setLibError(String(e.message ?? e)));
  };

  const busy = libJob?.status === "running";

  return (
    <div className="border border-border">
      <div className="flex items-start justify-between gap-4 border-b border-border p-5">
        <div className="min-w-0">
          <div className="text-sm font-semibold uppercase tracking-wide text-fg-strong">{t.settings.canonicalLibraryTitle}</div>
          <p className="mt-1 text-sm text-muted">
            {t.settings.canonicalLibraryBody}
          </p>
        </div>
      </div>
      <div className="space-y-3 p-5 text-sm">
        {libError && <Alert tone="danger">⚠ {libError}</Alert>}
        {libJob?.status === "error" && <Alert tone="danger">⚠ {libJob.error ?? t.settings.indexFailedFallback}</Alert>}
        <Button size="sm" onClick={runIndex} disabled={busy}>{busy ? t.settings.indexingLabel : t.settings.indexNowButton}</Button>
        {busy && (
          <p className="tnum text-sm text-muted">{t.settings.indexingProgress(libJob.processed, libJob.total)}</p>
        )}
        {libJob?.status === "done" && (
          <p className="text-sm text-fg">
            {t.settings.indexResultSummary(libJob.scanned, libJob.matched, libJob.created, libJob.duplicates, libJob.relinked, libJob.lost, libJob.failed)}
          </p>
        )}
      </div>
    </div>
  );
}

export default function Settings() {
  return <Suspense><SettingsInner /></Suspense>;
}
