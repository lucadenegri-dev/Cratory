"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Copy, Check, ExternalLink, Gauge, Plug, Music2, Sparkles, Database } from "lucide-react";
import {
  apiGet, apiPost, servicesStatus, SPOTIFY_LOGIN_URL,
  featureEnrichSummary,
  type ServiceStatus, type SpotifyStatus,
  type FeatureProviderStatus, type FeatureEnrichJob,
} from "@/lib/api";
import { Card, CardHeader, Button, Alert, Badge, Progress } from "@/components/ui";

const CATEGORY_ICON: Record<string, React.ReactNode> = {
  Streaming: <Music2 size={15} className="text-success" />,
  AI: <Sparkles size={15} className="text-primary" />,
  "Feature musicali": <Gauge size={15} className="text-info" />,
};

function statusPill(s: ServiceStatus) {
  if (s.connected === true) return <Badge tone="success">Collegato</Badge>;
  if (s.connected === false) return <Badge tone="warning">Da collegare</Badge>;
  if (s.configured) return <Badge tone="info">Configurato</Badge>;
  return <Badge tone="neutral">Non configurato</Badge>;
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

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Impostazioni</h1>
        <p className="mt-1 text-sm text-muted">Stato delle integrazioni esterne. Le chiavi si configurano in <code className="rounded bg-elevated px-1">backend/.env</code> e richiedono il riavvio del backend.</p>
      </header>

      {oauth === "connected" && <div className="mb-4"><Alert tone="success">✓ Account Spotify collegato.</Alert></div>}
      {oauth === "error" && <div className="mb-4"><Alert tone="danger">Login Spotify fallito ({params.get("detail")}).</Alert></div>}
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error} — il backend è attivo su :8000?</Alert></div>}

      <Card className="mb-4">
        <CardHeader title={<span className="flex items-center gap-2"><Plug size={16} className="text-primary" /> Servizi &amp; API</span>} subtitle="Tutte le integrazioni e il loro stato di connessione" />
        <div className="divide-y divide-border">
          {services?.map((s) => (
            <div key={s.key} className="p-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    {CATEGORY_ICON[s.category] ?? <Plug size={15} className="text-faint" />}
                    <span className="font-medium">{s.name}</span>
                    {statusPill(s)}
                  </div>
                  <p className="mt-1 text-sm text-muted">{s.detail}</p>
                  <p className="mt-1.5 text-xs text-faint">
                    {s.category} · {s.env.map((e) => <code key={e} className="mr-1 rounded bg-elevated px-1">{e}</code>)}
                    <a href={s.docs} target="_blank" rel="noreferrer" className="text-info hover:underline">docs ↗</a>
                  </p>
                </div>
                {s.key === "spotify" && (
                  <a href={SPOTIFY_LOGIN_URL}>
                    <Button size="sm" variant="outline"><ExternalLink size={14} /> {s.connected ? "Ricollega" : "Collega"}</Button>
                  </a>
                )}
              </div>

              {s.key === "spotify" && spotify?.configured && (
                <div className="mt-3 rounded-lg border border-border bg-bg p-3">
                  <p className="mb-1.5 text-xs text-muted">Redirect URI da incollare <strong>esatto</strong> nel dashboard Spotify:</p>
                  <div className="flex items-center gap-2">
                    <code className="flex-1 break-all rounded bg-elevated px-2 py-1 text-xs text-primary">{spotify.redirect_uri}</code>
                    <Button size="sm" variant="outline" onClick={copyRedirect}>{copied ? <><Check size={14} /> Copiato</> : <><Copy size={14} /> Copia</>}</Button>
                  </div>
                  {s.connected && <p className="mt-2 text-xs text-faint">Se l&apos;import playlist dà <code className="rounded bg-elevated px-1">403</code>, usa <strong>Ricollega</strong> per riautorizzare i permessi.</p>}
                </div>
              )}
            </div>
          ))}
          {!services && !error && <div className="p-5 text-sm text-muted">Caricamento…</div>}
        </div>
      </Card>

      <FeatureEnrichmentCard />
    </div>
  );
}

function FeatureEnrichmentCard() {
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
    try { setJob(await apiPost<FeatureEnrichJob>(`/api/enrichment/features?force=${force}`)); startPolling(); }
    catch (e) { setError(String((e as Error).message ?? e)); }
  }

  const busy = job?.status === "running";
  const pct = job && job.total > 0 ? Math.round((job.processed / job.total) * 100) : null;

  return (
    <Card className="mb-4">
      <CardHeader
        title={<span className="flex items-center gap-2"><Database size={16} className="text-info" /> Arricchimento feature musicali</span>}
        subtitle="BPM, tonalità, genere, mood, energia per le tracce importate"
        action={status && <Badge tone={status.configured ? "info" : "neutral"}>{status.configured ? status.provider ?? "attivo" : "nessun provider"}</Badge>}
      />
      <div className="space-y-3 p-5 text-sm">
        <p className="text-muted">Ricava BPM/key (GetSongBPM), label/genere (MusicBrainz) e genere/mood dai tag (Last.fm); l&apos;energia è stimata da BPM e danceability. Non sovrascrive mai i dati già presenti.</p>
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {status && !status.configured ? (
          <p className="text-faint">Configura almeno <code className="rounded bg-elevated px-1">GETSONGBPM_API_KEY</code> o <code className="rounded bg-elevated px-1">LASTFM_API_KEY</code> qui sopra per abilitare l&apos;arricchimento.</p>
        ) : (
          <div className="flex gap-2">
            <Button size="sm" onClick={() => run(false)} disabled={busy}>{busy ? "In corso…" : "Arricchisci feature"}</Button>
            <Button size="sm" variant="outline" onClick={() => run(true)} disabled={busy}>Forza</Button>
          </div>
        )}
        {busy && job && (
          <div>
            <div className="mb-1 flex justify-between text-xs text-muted"><span>Analizzo le tracce…</span><span className="tnum">{job.processed}/{job.total || "?"}{pct != null ? ` (${pct}%)` : ""}</span></div>
            <Progress value={pct} />
          </div>
        )}
        {job?.status === "done" && job.result && (
          <p className="text-sm text-success">✓ {featureEnrichSummary(job.result)}.</p>
        )}
      </div>
    </Card>
  );
}

export default function Settings() {
  return <Suspense><SettingsInner /></Suspense>;
}
