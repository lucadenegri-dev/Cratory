"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Copy, Check, ExternalLink } from "lucide-react";
import {
  apiGet, servicesStatus, setSoundcloudUsername, soundcloudStatus, SPOTIFY_LOGIN_URL, startLibraryIndex,
  type ServiceStatus, type SoundCloudStatus, type SpotifyStatus,
} from "@/lib/api";
import { Alert, Button, Card, CardHeader, Field, Input, Loading, Spinner } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { useI18n } from "@/lib/i18n";
import { cn } from "@/lib/cn";

function statusLabel(s: ServiceStatus): { text: string; strong: boolean } {
  if (s.connected === true) return { text: "Collegato", strong: true };
  if (s.connected === false) return { text: "Da collegare", strong: false };
  if (s.configured) return { text: "Configurato", strong: true };
  return { text: "Non configurato", strong: false };
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
      <p>Le chiavi si configurano in <code className="rounded-none bg-elevated px-1">backend/.env</code> e richiedono il riavvio del backend.</p>
    </div>
  );

  return (
    <PageLayout title="Impostazioni" marginaliaTitle="Aiuto" marginalia={marginalia}>
      {oauth === "connected" && <div className="mb-4"><Alert tone="info">✓ Account Spotify collegato.</Alert></div>}
      {oauth === "error" && <div className="mb-4"><Alert tone="danger">Login Spotify fallito ({params.get("detail")}).</Alert></div>}
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error} — il backend è attivo su :8000?</Alert></div>}

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

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">Servizi &amp; API</div>
      <div className="border border-border">
        {services?.map((s, i) => {
          const st = statusLabel(s);
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
                      <Button size="sm" variant="outline"><ExternalLink size={14} /> {s.connected ? "Ricollega" : "Collega"}</Button>
                    </a>
                  )}
                </div>
              </div>

              {s.key === "spotify" && spotify?.configured && (
                <div className="mt-3 border border-border bg-bg p-3">
                  <p className="mb-1.5 text-xs text-muted">Redirect URI da incollare <strong>esatto</strong> nel dashboard Spotify:</p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 break-all bg-elevated px-2 py-1 text-xs text-fg">{spotify.redirect_uri}</code>
                    <Button size="sm" variant="outline" onClick={copyRedirect}>{copied ? <><Check size={14} /> Copiato</> : <><Copy size={14} /> Copia</>}</Button>
                  </div>
                  {s.connected && <p className="mt-2 text-xs text-muted">Se l&apos;import playlist dà <code className="rounded-none bg-elevated px-1">403</code>, usa <strong>Ricollega</strong> per riautorizzare i permessi.</p>}
                </div>
              )}
            </div>
          );
        })}
        {!services && !error && <div className="px-5"><Loading /></div>}
      </div>

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">Libreria (disco)</div>
      <LibraryIndexCard />

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">SoundCloud</div>
      <SoundCloudCard />
    </PageLayout>
  );
}

function SoundCloudCard() {
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
        subtitle="Username per l'import dei like. Le playlist si importano incollando l'URL."
      />
      <div className="grid gap-3 p-4">
        {status && !status.available && (
          <Alert tone="warning">yt-dlp non disponibile nel backend: l&apos;import SoundCloud non funzionerà.</Alert>
        )}
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        <Field label="Username SoundCloud">
          <div className="flex items-center gap-2">
            <Input
              className="flex-1"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="es. luca-denegri"
              disabled={saving}
            />
            <Button size="sm" onClick={save} disabled={saving || username.trim() === ""}>
              {saving ? <Spinner /> : "Salva"}
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
          <div className="text-sm font-semibold uppercase tracking-wide text-fg-strong">Libreria canonica</div>
          <p className="mt-1 text-sm text-muted">
            La libreria canonica è la cartella LIBRARY_ROOT sul disco: indicizzala dopo ogni riorganizzazione.
          </p>
        </div>
      </div>
      <div className="space-y-3 p-5 text-sm">
        {libError && <Alert tone="danger">⚠ {libError}</Alert>}
        {libJob?.status === "error" && <Alert tone="danger">⚠ {libJob.error ?? "Indicizzazione fallita"}</Alert>}
        <Button size="sm" onClick={runIndex} disabled={busy}>{busy ? "In corso…" : "Indicizza ora"}</Button>
        {busy && (
          <p className="tnum text-sm text-muted">{libJob.processed}/{libJob.total} file processati…</p>
        )}
        {libJob?.status === "done" && (
          <p className="text-sm text-fg">
            ✓ {libJob.scanned} file · {libJob.matched} riagganciate · {libJob.created} nuove ·{" "}
            {libJob.duplicates} duplicati · {libJob.relinked} path aggiornati · {libJob.lost} perse ·{" "}
            {libJob.failed} errori
          </p>
        )}
      </div>
    </div>
  );
}

export default function Settings() {
  return <Suspense><SettingsInner /></Suspense>;
}
