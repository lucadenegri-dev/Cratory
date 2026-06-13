"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  apiGet, apiPost, SPOTIFY_LOGIN_URL,
  type EnrichJobStatus, type EnrichReport, type SpotifyStatus,
} from "@/lib/api";

function SettingsInner() {
  const params = useSearchParams();
  const oauthResult = params.get("spotify"); // connected | error
  const [status, setStatus] = useState<SpotifyStatus | null>(null);
  const [report, setReport] = useState<EnrichReport | null>(null);
  const [job, setJob] = useState<EnrichJobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(() => {
    apiGet<SpotifyStatus>("/api/spotify/status")
      .then((s) => { setStatus(s); setError(null); })
      .catch((e) => { setStatus(null); setError(String(e.message ?? e)); });
  }, []);
  useEffect(load, [load]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  // Riaggancia un job già in corso (es. dopo un refresh della pagina) e pulisce al unmount.
  useEffect(() => {
    apiGet<EnrichJobStatus>("/api/spotify/enrich/status")
      .then((s) => { if (s.status === "running") startPolling(); })
      .catch(() => {});
    return stopPolling;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function startPolling() {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const s = await apiGet<EnrichJobStatus>("/api/spotify/enrich/status");
        setJob(s);
        if (s.status === "done") {
          stopPolling();
          setReport(s.result);
          load();
        } else if (s.status === "error") {
          stopPolling();
          setError(s.error ?? "Enrichment fallito");
        }
      } catch (e) {
        stopPolling();
        setError(String((e as Error).message ?? e));
      }
    }, 800);
  }

  async function enrich(force = false) {
    setError(null);
    setReport(null);
    try {
      const started = await apiPost<EnrichJobStatus>(`/api/spotify/enrich?force=${force}`);
      setJob(started);
      startPolling();
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }

  const busy = job?.status === "running";
  const pct = job && job.total > 0 ? Math.round((job.processed / job.total) * 100) : 0;

  async function copyRedirect() {
    if (!status?.redirect_uri) return;
    await navigator.clipboard.writeText(status.redirect_uri);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="max-w-3xl">
      <h2 className="mb-4 text-2xl font-bold">Settings</h2>

      {oauthResult === "connected" && (
        <p className="mb-4 rounded bg-emerald-950 p-3 text-sm text-emerald-300">✓ Account Spotify collegato.</p>
      )}
      {oauthResult === "error" && (
        <p className="mb-4 rounded bg-red-950 p-3 text-sm text-red-300">⚠ Login Spotify fallito ({params.get("detail")}).</p>
      )}

      <section className="mb-6 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <h3 className="mb-2 font-semibold">Spotify</h3>

        {!status && (
          <div className="rounded bg-red-950 p-3 text-sm text-red-300">
            ⚠ Backend non raggiungibile su <code className="rounded bg-zinc-800 px-1">:8000</code>.
            Avvia il backend (<code className="rounded bg-zinc-800 px-1">uvicorn app.main:app --port 8000</code> da <code className="rounded bg-zinc-800 px-1">backend/</code>), poi{" "}
            <button onClick={load} className="underline hover:text-white">Riprova</button>.
          </div>
        )}

        {status && !status.configured && (
          <div className="text-sm text-zinc-300">
            <p className="mb-2 rounded bg-amber-950 p-3 text-amber-300">
              Credenziali non configurate. Crea un&apos;app su{" "}
              <a href="https://developer.spotify.com/dashboard" target="_blank" rel="noreferrer" className="underline">developer.spotify.com</a>{" "}
              con redirect URI <code className="rounded bg-zinc-800 px-1">http://127.0.0.1:8000/api/spotify/callback</code>{" "}
              (Spotify non accetta più <code className="rounded bg-zinc-800 px-1">localhost</code>),
              poi imposta in <code className="rounded bg-zinc-800 px-1">backend/.env</code>:
            </p>
            <pre className="rounded bg-zinc-950 p-3 text-xs">{`SPOTIFY_CLIENT_ID=...\nSPOTIFY_CLIENT_SECRET=...`}</pre>
            <p className="mt-2 text-zinc-400">Riavvia il backend e ricarica questa pagina.</p>
          </div>
        )}

        {status?.configured && (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap items-center gap-3">
              <span className={`h-2.5 w-2.5 rounded-full ${status.user_connected ? "bg-emerald-500" : "bg-zinc-600"}`} />
              <span>{status.user_connected ? "Account collegato (puoi creare playlist)" : "Account non collegato — serve solo per creare playlist"}</span>
              {!status.user_connected && (
                <a href={SPOTIFY_LOGIN_URL} className="rounded bg-green-700 px-3 py-1.5 hover:bg-green-600">Collega Spotify</a>
              )}
            </div>

            {/* Redirect URI: deve combaciare esattamente col dashboard Spotify */}
            <div className="rounded border border-zinc-800 bg-zinc-950 p-3">
              <p className="mb-1 text-zinc-400">
                Redirect URI da incollare <strong>esatto</strong> nel dashboard Spotify
                (App → Settings → Redirect URIs → Add → Save):
              </p>
              <div className="flex items-center gap-2">
                <code className="flex-1 break-all rounded bg-zinc-800 px-2 py-1 text-emerald-300">{status.redirect_uri}</code>
                <button onClick={copyRedirect} className="shrink-0 rounded bg-zinc-700 px-3 py-1 hover:bg-zinc-600">
                  {copied ? "Copiato ✓" : "Copia"}
                </button>
              </div>
              {oauthResult === "error" && (
                <p className="mt-2 text-amber-400">
                  Errore <code className="rounded bg-zinc-800 px-1">redirect_uri: Not matching configuration</code>:
                  il valore qui sopra non è ancora registrato (identico, incluso <code className="rounded bg-zinc-800 px-1">http://</code>,
                  porta e percorso) nel dashboard Spotify. Aggiungilo, premi <em>Save</em>, attendi qualche secondo e riprova.
                </p>
              )}
            </div>

            <div className="border-t border-zinc-800 pt-4">
              <h4 className="mb-1 font-medium">Enrichment metadata</h4>
              <p className="mb-3 text-zinc-400">
                Completa titolo, artista, album, cover e generi delle tracce Spotify.
                Non tocca mai BPM e tonalità (vengono da Rekordbox). Non richiede il login.
              </p>
              <div className="flex gap-2">
                <button onClick={() => enrich(false)} disabled={busy}
                  className="rounded bg-emerald-600 px-4 py-2 font-semibold hover:bg-emerald-500 disabled:opacity-50">
                  {busy ? "Enrichment in corso…" : "Arricchisci libreria"}
                </button>
                <button onClick={() => enrich(true)} disabled={busy}
                  className="rounded bg-zinc-800 px-4 py-2 hover:bg-zinc-700 disabled:opacity-50">
                  Forza ri-enrichment
                </button>
              </div>

              {busy && job && (
                <div className="mt-3">
                  <div className="mb-1 flex justify-between text-xs text-zinc-400">
                    <span>Recupero {job.phase ?? "dati"} da Spotify…</span>
                    <span>{job.processed}/{job.total || "?"}{job.total ? ` (${pct}%)` : ""}</span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded bg-zinc-800">
                    <div className="h-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
                  </div>
                </div>
              )}

              {report && (
                <p className="mt-3 rounded bg-emerald-950 p-3 text-emerald-300">
                  {report.skipped_already_enriched
                    ? "Tutto già arricchito (cache). Usa “Forza ri-enrichment” per riscaricare."
                    : `✓ ${report.enriched} tracce arricchite, ${report.artists_updated} artisti aggiornati${report.not_found ? `, ${report.not_found} ID non trovati su Spotify` : ""}.`}
                </p>
              )}
            </div>
          </div>
        )}

        {error && <p className="mt-3 rounded bg-red-950 p-3 text-sm text-red-300">⚠ {error}</p>}
      </section>

      <section className="rounded-lg border border-zinc-800 bg-zinc-900 p-4 text-sm text-zinc-400">
        <h3 className="mb-2 font-semibold text-zinc-200">Integrazioni future</h3>
        <p>Discogs, MusicBrainz e AI Set Agent arriveranno con MVP 3 e 4. Le relative chiavi si configurano in <code className="rounded bg-zinc-800 px-1">backend/.env</code>.</p>
      </section>
    </div>
  );
}

export default function Settings() {
  return (
    <Suspense>
      <SettingsInner />
    </Suspense>
  );
}
