"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Copy, Check, ExternalLink } from "lucide-react";
import {
  apiGet, apiPost, servicesStatus, SPOTIFY_LOGIN_URL,
  featureEnrichSummary,
  type ServiceStatus, type SpotifyStatus,
  type FeatureProviderStatus, type FeatureEnrichJob,
} from "@/lib/api";
import { Button, Alert, Equalizer } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";

function statusLabel(s: ServiceStatus): { text: string; strong: boolean } {
  if (s.connected === true) return { text: "Collegato", strong: true };
  if (s.connected === false) return { text: "Da collegare", strong: false };
  if (s.configured) return { text: "Configurato", strong: true };
  return { text: "Non configurato", strong: false };
}

function SettingsInner() {
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
      <p>L&apos;arricchimento non sovrascrive mai i valori di BPM/key che inserisci a mano.</p>
    </div>
  );

  return (
    <PageLayout title="Impostazioni" marginaliaTitle="Aiuto" marginalia={marginalia}>
      {oauth === "connected" && <div className="mb-4"><Alert tone="info">✓ Account Spotify collegato.</Alert></div>}
      {oauth === "error" && <div className="mb-4"><Alert tone="danger">Login Spotify fallito ({params.get("detail")}).</Alert></div>}
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error} — il backend è attivo su :8000?</Alert></div>}

      <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">Servizi &amp; API</div>
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
        {!services && !error && <div className="flex items-center gap-2 p-5 text-sm text-muted"><Equalizer className="h-3.5 w-3.5" /> Caricamento…</div>}
      </div>

      <div className="mb-2 mt-8 text-[10px] uppercase tracking-wider text-muted">Arricchimento</div>
      <FeatureEnrichmentCard />
    </PageLayout>
  );
}

function FeatureEnrichmentCard() {
  const jobs = useJobs();
  const [status, setStatus] = useState<FeatureProviderStatus | null>(null);
  const [job, setJob] = useState<FeatureEnrichJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stop = useCallback(() => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } }, []);
  const startPolling = useCallback(() => {
    stop();
    pollRef.current = setInterval(async () => {
      try {
        const s = await apiGet<FeatureEnrichJob>("/api/enrichment/features/status");
        setJob(s);
        if (s.status === "done" || s.status === "idle") stop();
        else if (s.status === "error") { stop(); setError(s.error ?? "Enrichment fallito"); }
      } catch (e) { stop(); setError(String((e as Error).message ?? e)); }
    }, 800);
  }, [stop]);

  useEffect(() => {
    apiGet<FeatureProviderStatus>("/api/enrichment/status").then(setStatus).catch(() => setStatus({ configured: false, provider: null }));
    apiGet<FeatureEnrichJob>("/api/enrichment/features/status").then((s) => { setJob(s); if (s.status === "running") startPolling(); }).catch(() => {});
    return stop;
  }, [startPolling, stop]);

  async function run(force: boolean) {
    setError(null);
    try { setJob(await apiPost<FeatureEnrichJob>(`/api/enrichment/features?force=${force}`)); startPolling(); jobs.refresh(); }
    catch (e) { setError(String((e as Error).message ?? e)); }
  }

  const busy = job?.status === "running";

  return (
    <div className="border border-border">
      <div className="flex items-start justify-between gap-4 border-b border-border p-5">
        <div className="min-w-0">
          <div className="text-sm font-semibold uppercase tracking-wide text-fg-strong">Feature musicali</div>
          <p className="mt-1 text-sm text-muted">BPM, tonalità, genere, mood, energia per le tracce importate.</p>
        </div>
        {status && <span className="shrink-0 text-[10px] uppercase tracking-wider text-muted">{status.configured ? status.provider ?? "attivo" : "nessun provider"}</span>}
      </div>
      <div className="space-y-3 p-5 text-sm">
        <p className="text-muted">Ricava BPM via ISRC (Deezer), analisi audio reale via MusicBrainz + AcousticBrainz (BPM, tonalità, mood, danceability) e genere/mood dai tag (Last.fm); l&apos;energia è stimata da BPM e danceability quando manca. Non sovrascrive i valori che inserisci a mano.</p>
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {status && !status.configured ? (
          <p className="text-muted">Configura almeno <code className="rounded-none bg-elevated px-1">GETSONGBPM_API_KEY</code> o <code className="rounded-none bg-elevated px-1">LASTFM_API_KEY</code> qui sopra per abilitare l&apos;arricchimento.</p>
        ) : (
          <div className="flex gap-2">
            <Button size="sm" onClick={() => run(false)} disabled={busy}>{busy ? "In corso…" : "Arricchisci feature"}</Button>
            <Button size="sm" variant="outline" onClick={() => run(true)} disabled={busy}>Forza</Button>
          </div>
        )}
        {job?.status === "done" && job.result && (
          <p className="text-sm text-fg">✓ {featureEnrichSummary(job.result)}.</p>
        )}
      </div>
    </div>
  );
}

export default function Settings() {
  return <Suspense><SettingsInner /></Suspense>;
}
