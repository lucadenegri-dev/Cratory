"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import {
  apiGet, apiPost, SPOTIFY_LOGIN_URL,
  type EnrichReport, type SpotifyStatus,
} from "@/lib/api";

function SettingsInner() {
  const params = useSearchParams();
  const oauthResult = params.get("spotify"); // connected | error
  const [status, setStatus] = useState<SpotifyStatus | null>(null);
  const [report, setReport] = useState<EnrichReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<SpotifyStatus>("/api/spotify/status").then(setStatus).catch((e) => setError(String(e.message ?? e)));
  }, []);
  useEffect(load, [load]);

  async function enrich(force = false) {
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      setReport(await apiPost<EnrichReport>(`/api/spotify/enrich?force=${force}`));
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setBusy(false);
    }
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
            <div className="flex items-center gap-3">
              <span className={`h-2.5 w-2.5 rounded-full ${status.user_connected ? "bg-emerald-500" : "bg-zinc-600"}`} />
              <span>{status.user_connected ? "Account collegato (puoi creare playlist)" : "Account non collegato — serve solo per creare playlist"}</span>
              {!status.user_connected && (
                <a href={SPOTIFY_LOGIN_URL} className="rounded bg-green-700 px-3 py-1.5 hover:bg-green-600">Collega Spotify</a>
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
