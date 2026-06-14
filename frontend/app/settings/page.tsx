"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Copy, Check, ExternalLink, Sparkles, Music2, Database, Gauge } from "lucide-react";
import {
  apiGet, apiPost, SPOTIFY_LOGIN_URL,
  type AiStatus, type SpotifyStatus,
  type FeatureProviderStatus, type FeatureEnrichJob,
} from "@/lib/api";
import { Card, CardHeader, Button, Alert, Badge, Progress } from "@/components/ui";

function Dot({ on }: { on: boolean }) {
  return <span className={`h-2.5 w-2.5 rounded-full ${on ? "bg-success" : "bg-faint"}`} />;
}

function SettingsInner() {
  const params = useSearchParams();
  const oauth = params.get("spotify");
  const [spotify, setSpotify] = useState<SpotifyStatus | null>(null);
  const [ai, setAi] = useState<AiStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    apiGet<SpotifyStatus>("/api/spotify/status").then((s) => { setSpotify(s); setError(null); }).catch((e) => { setSpotify(null); setError(String(e.message ?? e)); });
    apiGet<AiStatus>("/api/ai/status").then(setAi).catch(() => setAi({ configured: false, model: null }));
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
        <p className="mt-1 text-sm text-muted">Integrazioni esterne. Le chiavi si configurano in <code className="rounded bg-elevated px-1">backend/.env</code>.</p>
      </header>

      {oauth === "connected" && <div className="mb-4"><Alert tone="success">✓ Account Spotify collegato.</Alert></div>}
      {oauth === "error" && <div className="mb-4"><Alert tone="danger">Login Spotify fallito ({params.get("detail")}).</Alert></div>}
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {!spotify && (
        <Card className="mb-4"><div className="p-5 text-sm">
          <Alert tone="danger">Backend non raggiungibile su :8000. Avvia <code className="rounded bg-elevated px-1">uvicorn app.main:app --port 8000</code> e <button onClick={load} className="underline">riprova</button>.</Alert>
        </div></Card>
      )}

      {/* Spotify */}
      <Card className="mb-4">
        <CardHeader
          title={<span className="flex items-center gap-2"><Music2 size={16} className="text-success" /> Spotify</span>}
          action={spotify && <Badge tone={spotify.configured ? "success" : "neutral"}>{spotify.configured ? "configurato" : "non configurato"}</Badge>}
        />
        <div className="space-y-4 p-5 text-sm">
          {spotify && !spotify.configured && (
            <div className="space-y-2 text-muted">
              <p>Crea un&apos;app su <a href="https://developer.spotify.com/dashboard" target="_blank" rel="noreferrer" className="text-info hover:underline">developer.spotify.com</a> e imposta in <code className="rounded bg-elevated px-1">backend/.env</code>:</p>
              <pre className="rounded-lg border border-border bg-bg p-3 text-xs">SPOTIFY_CLIENT_ID=…{"\n"}SPOTIFY_CLIENT_SECRET=…</pre>
            </div>
          )}

          {spotify?.configured && (
            <>
              <div className="flex flex-wrap items-center gap-3">
                <span className="flex items-center gap-2"><Dot on={spotify.user_connected} /> {spotify.user_connected ? "Account collegato" : "Account non collegato (serve solo per creare playlist)"}</span>
                {!spotify.user_connected && <a href={SPOTIFY_LOGIN_URL}><Button size="sm" variant="outline"><ExternalLink size={14} /> Collega Spotify</Button></a>}
              </div>

              <div className="rounded-lg border border-border bg-bg p-3">
                <p className="mb-1.5 text-muted">Redirect URI da incollare <strong>esatto</strong> nel dashboard Spotify:</p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 break-all rounded bg-elevated px-2 py-1 text-xs text-primary">{spotify.redirect_uri}</code>
                  <Button size="sm" variant="outline" onClick={copyRedirect}>{copied ? <><Check size={14} /> Copiato</> : <><Copy size={14} /> Copia</>}</Button>
                </div>
              </div>

              <p className="text-muted">
                I metadata (titolo, artista, album, cover, ISRC, durata) arrivano già con l&apos;import della playlist.
                BPM, tonalità, genere, mood ed energia si ricavano dalla sezione <strong>Feature musicali</strong> qui sotto.
              </p>
            </>
          )}
        </div>
      </Card>

      {/* AI */}
      <Card className="mb-4">
        <CardHeader
          title={<span className="flex items-center gap-2"><Sparkles size={16} className="text-primary" /> AI Set Agent</span>}
          action={ai && <Badge tone={ai.configured ? "primary" : "neutral"}>{ai.configured ? ai.model ?? "configurato" : "non configurato"}</Badge>}
        />
        <div className="p-5 text-sm text-muted">
          {ai?.configured
            ? <p>Attiva. Usa il toggle nel <a href="/set-builder" className="text-info hover:underline">Set Builder</a> per generare set dal prompt libero.</p>
            : <p>Imposta <code className="rounded bg-elevated px-1">AI_API_KEY</code> (e opzionale <code className="rounded bg-elevated px-1">AI_MODEL</code>) in <code className="rounded bg-elevated px-1">backend/.env</code>, poi riavvia il backend.</p>}
        </div>
      </Card>

      {/* Feature musicali (BPM/key) */}
      <FeatureEnrichmentCard />

      {/* Future */}
      <Card>
        <CardHeader title={<span className="flex items-center gap-2"><Database size={16} className="text-faint" /> Integrazioni future</span>} />
        <div className="p-5 text-sm text-muted">Discogs e MusicBrainz (Library Expansion) arriveranno con l&apos;MVP 4.</div>
      </Card>
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
        title={<span className="flex items-center gap-2"><Gauge size={16} className="text-info" /> Feature musicali (BPM, key, genere, mood, energia)</span>}
        action={status && <Badge tone={status.configured ? "info" : "neutral"}>{status.configured ? status.provider ?? "configurato" : "non configurato"}</Badge>}
      />
      <div className="space-y-3 p-5 text-sm">
        <p className="text-muted">Ricava BPM e tonalità (GetSongBPM), genere/label (MusicBrainz), genere e mood dai tag (Last.fm); l&apos;energia è stimata da BPM e danceability. Non sovrascrive mai i dati già presenti.</p>
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {status && !status.configured ? (
          <pre className="rounded-lg border border-border bg-bg p-3 text-xs">GETSONGBPM_API_KEY=…  <span className="text-faint"># BPM/key — gratis su getsongbpm.com/api</span>{"\n"}LASTFM_API_KEY=…      <span className="text-faint"># genere/mood — gratis su last.fm/api</span></pre>
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
          <p className="text-sm text-success">✓ {job.result.enriched} tracce arricchite{job.result.not_found ? `, ${job.result.not_found} non trovate` : ""} su {job.result.total}.</p>
        )}
      </div>
    </Card>
  );
}

export default function Settings() {
  return <Suspense><SettingsInner /></Suspense>;
}
