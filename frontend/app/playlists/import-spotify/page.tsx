"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, RefreshCw, Heart } from "lucide-react";
import {
  apiGet,
  importPlaylist,
  listSpotifyPlaylists,
  listImportedPlaylists,
  SPOTIFY_LOGIN_URL,
  type SpotifyPlaylistRef,
  type SpotifyStatus,
} from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ImportSpotifyPage() {
  const router = useRouter();
  const [spotify, setSpotify] = useState<SpotifyStatus | null>(null);
  const [available, setAvailable] = useState<SpotifyPlaylistRef[] | null>(null);
  const [imported, setImported] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<SpotifyStatus>("/api/spotify/status").then(setSpotify).catch((e) => setError(err(e)));
    listImportedPlaylists()
      .then((pls) =>
        setImported(new Set(pls.filter((p) => p.platform_playlist_id).map((p) => p.platform_playlist_id!))),
      )
      .catch(() => {});
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

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>Spotify fornisce identità traccia, metadata editoriali, cover, durata, ISRC e URL.</p>
      <p>BPM, key e feature di mixing <span className="text-fg">non</span> arrivano da Spotify: vengono aggiunti dall&apos;arricchimento dopo l&apos;import.</p>
    </div>
  );

  return (
    <PageLayout title="Import — Spotify" marginaliaTitle="Note" marginalia={marginalia}>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Playlist
      </Link>
      <p className="mb-6 text-sm text-muted">
        L&apos;import non aggiunge file alla libreria: porta dentro i lead della playlist,
        da arricchire, scaricare e organizzare.
      </p>

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
          <div className="px-5 py-4">
            {!available && <p className="text-sm text-muted">Premi “Carica” per elencare le tue playlist.</p>}
            {available && available.length === 0 && <p className="text-sm text-muted">Nessuna playlist trovata.</p>}
            <div className="grid gap-2">
              {available?.map((p) => {
                const alreadyImported = imported.has(p.platform_playlist_id);
                return (
                  <div key={p.platform_playlist_id} className="flex items-center justify-between gap-3 rounded-none border border-border px-3 py-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium">{p.name}</div>
                      <div className="text-xs text-faint">
                        {p.track_count} tracce{p.owner ? ` · ${p.owner}` : ""}{alreadyImported ? " · importata" : ""}
                      </div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      className="w-28 justify-center"
                      onClick={() => doImport(p.platform_playlist_id, p.name)}
                      disabled={busy !== null}
                    >
                      {busy === p.platform_playlist_id ? (
                        <Spinner />
                      ) : alreadyImported ? (
                        <><RefreshCw size={15} /> Aggiorna</>
                      ) : (
                        <><Download size={15} /> Importa</>
                      )}
                    </Button>
                  </div>
                );
              })}
            </div>
          </div>
        </Card>
      )}
    </PageLayout>
  );
}
