"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, RefreshCw, Heart } from "lucide-react";
import {
  apiGet,
  errText,
  importPlaylist,
  listSpotifyPlaylists,
  listImportedPlaylists,
  SPOTIFY_LOGIN_URL,
  type SpotifyPlaylistRef,
  type SpotifyStatus,
} from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { PlaylistCover } from "@/components/playlist-cover";
import { useJobs } from "@/components/jobs-provider";
import { useT } from "@/lib/i18n";

export default function ImportSpotifyPage() {
  const t = useT();
  const router = useRouter();
  const jobs = useJobs();
  const [spotify, setSpotify] = useState<SpotifyStatus | null>(null);
  const [available, setAvailable] = useState<SpotifyPlaylistRef[] | null>(null);
  const [imported, setImported] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    apiGet<SpotifyStatus>("/api/spotify/status").then(setSpotify).catch((e) => setError(errText(e)));
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
      setError(errText(e));
    } finally {
      setBusy(null);
    }
  };

  const doImport = async (playlistId: string, label: string) => {
    setError(null);
    setBusy(playlistId);
    try {
      await importPlaylist(playlistId);
      // L'import gira in background (barra job globale): torniamo all'elenco
      // dove viene mostrato l'avanzamento.
      jobs.refresh();
      router.push("/playlists");
    } catch (e) {
      setError(t.playlists.importSpotify.importFailed(label, errText(e)));
      setBusy(null);
    }
  };

  const connected = spotify?.configured && spotify?.user_connected;
  const isf = t.playlists.importSpotify;

  // Carica automaticamente l'elenco appena lo stato Spotify risulta connesso.
  useEffect(() => {
    if (!connected) return;
    listSpotifyPlaylists()
      .then(setAvailable)
      .catch((e) => setError(errText(e)));
  }, [connected]);

  const filtered = available?.filter((p) => p.name.toLowerCase().includes(filter.trim().toLowerCase()));

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>{isf.noteIdentity}</p>
      <p>{isf.noteBpmKeyPrefix} <span className="text-fg">{isf.noteBpmKeyNot}</span> {isf.noteBpmKeySuffix}</p>
    </div>
  );

  return (
    <PageLayout title={isf.pageTitle} marginaliaTitle={t.playlists.marginaliaNotes} marginalia={marginalia}>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> {t.playlists.backLink}
      </Link>
      <p className="mb-6 text-sm text-muted">
        {isf.intro}
      </p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {!connected && (
        <div className="mb-6">
          <Alert tone="info">
            {spotify && !spotify.configured
              ? isf.notConfigured
              : isf.connectHint}
            {spotify?.configured && (
              <a href={SPOTIFY_LOGIN_URL} className="ml-2 font-medium underline">{isf.connectButton}</a>
            )}
          </Alert>
        </div>
      )}

      {connected && (
        <Card>
          <CardHeader
            title={isf.yourPlaylistsTitle}
            subtitle={isf.selectSubtitle}
            action={
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => router.push("/playlists/import-spotify/liked")} disabled={busy !== null}>
                  <Heart size={15} /> {isf.likedButton}
                </Button>
                <Button size="sm" onClick={loadAvailable} disabled={busy !== null}>
                  {busy === "available" ? <Spinner /> : <RefreshCw size={15} />} {isf.loadButton}
                </Button>
              </div>
            }
          />
          <div className="px-5 py-4">
            {!available && !error && <Loading />}
            {!available && error && <p className="text-sm text-muted">{isf.pressLoadHint}</p>}
            {available && available.length === 0 && <p className="text-sm text-muted">{isf.noPlaylistsFound}</p>}
            {available && available.length > 0 && (
              <div className="mb-3">
                <Input
                  className="h-9"
                  placeholder={isf.filterPlaceholder}
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                />
              </div>
            )}
            {available && available.length > 0 && filtered?.length === 0 && (
              <p className="text-sm text-muted">{isf.filterNoMatch}</p>
            )}
            <div className="grid gap-2">
              {filtered?.map((p) => {
                const alreadyImported = imported.has(p.platform_playlist_id);
                return (
                  <div key={p.platform_playlist_id} className="flex items-center justify-between gap-3 rounded-none border border-border px-3 py-2">
                    <div className="flex min-w-0 items-center gap-3">
                      <PlaylistCover artworkUrl={p.artwork_url} platform="spotify" className="h-9 w-9 shrink-0" iconSize={15} placeholderClassName="bg-elevated" />
                      <div className="min-w-0">
                        <div className="truncate text-sm font-medium">{p.name}</div>
                        <div className="text-xs text-faint">
                          {t.playlists.trackCount(p.track_count)}{p.owner ? ` · ${p.owner}` : ""}{alreadyImported ? ` · ${isf.alreadyImportedSuffix}` : ""}
                        </div>
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
                        <><RefreshCw size={15} /> {isf.updateButton}</>
                      ) : (
                        <><Download size={15} /> {isf.importButton}</>
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
