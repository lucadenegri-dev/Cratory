"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, RefreshCw, Heart } from "lucide-react";
import {
  apiGet,
  importPlaylist,
  listSpotifyPlaylists,
  SPOTIFY_LOGIN_URL,
  type SpotifyPlaylistRef,
  type SpotifyStatus,
} from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner } from "@/components/ui";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ImportSpotifyPage() {
  const router = useRouter();
  const [spotify, setSpotify] = useState<SpotifyStatus | null>(null);
  const [available, setAvailable] = useState<SpotifyPlaylistRef[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<SpotifyStatus>("/api/spotify/status").then(setSpotify).catch((e) => setError(err(e)));
  }, []);

  const loadAvailable = async () => {
    setError(null);
    setBusy("available");
    try {
      setAvailable(await listSpotifyPlaylists());
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(null);
    }
  };

  const doImport = async (playlistId: string, label: string) => {
    setError(null);
    setBusy(playlistId);
    try {
      await importPlaylist(playlistId);
      // L'arricchimento parte da solo lato backend: torniamo all'elenco dove
      // viene mostrato l'avanzamento.
      router.push("/playlists");
    } catch (e) {
      setError(`Import di ${label} fallito: ${err(e)}`);
      setBusy(null);
    }
  };

  const connected = spotify?.configured && spotify?.user_connected;

  return (
    <div>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Playlist
      </Link>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Importa da Spotify</h1>
        <p className="mt-1 text-sm text-muted">Scegli una delle tue playlist Spotify: verrà importata e arricchita automaticamente.</p>
      </header>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {!connected && (
        <div className="mb-6">
          <Alert tone="info">
            {spotify && !spotify.configured
              ? "Spotify non configurato: imposta le credenziali in Impostazioni."
              : "Collega l'account Spotify per leggere le tue playlist."}
            {spotify?.configured && (
              <a href={SPOTIFY_LOGIN_URL} className="ml-2 font-medium underline">Collega Spotify →</a>
            )}
          </Alert>
        </div>
      )}

      {connected && (
        <Card>
          <CardHeader
            title="Le tue playlist"
            subtitle="Seleziona una playlist da importare"
            action={
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => doImport("liked", "Brani che ti piacciono")} disabled={busy !== null}>
                  <Heart size={15} /> Liked
                </Button>
                <Button size="sm" onClick={loadAvailable} disabled={busy !== null}>
                  {busy === "available" ? <Spinner /> : <RefreshCw size={15} />} Carica
                </Button>
              </div>
            }
          />
          <div className="p-4">
            {!available && <p className="text-sm text-muted">Premi “Carica” per elencare le tue playlist.</p>}
            {available && available.length === 0 && <p className="text-sm text-muted">Nessuna playlist trovata.</p>}
            <div className="grid gap-2">
              {available?.map((p) => (
                <div key={p.platform_playlist_id} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium">{p.name}</div>
                    <div className="text-xs text-faint">{p.track_count} tracce{p.owner ? ` · ${p.owner}` : ""}</div>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => doImport(p.platform_playlist_id, p.name)} disabled={busy !== null}>
                    {busy === p.platform_playlist_id ? <Spinner /> : <Download size={15} />} Importa
                  </Button>
                </div>
              ))}
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
