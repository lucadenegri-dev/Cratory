"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, ListPlus, RefreshCw, Heart, AlertTriangle, Info, Music2, ClipboardList } from "lucide-react";
import {
  apiGet,
  importPlaylist,
  importManualPlaylist,
  listImportedPlaylists,
  listSpotifyPlaylists,
  playlistGaps,
  SPOTIFY_LOGIN_URL,
  type GapAnalysis,
  type Playlist,
  type SpotifyPlaylistRef,
  type SpotifyStatus,
} from "@/lib/api";
import { Card, CardHeader, Badge, Alert, Button, EmptyState, Spinner, Input, Textarea, Field } from "@/components/ui";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function PlaylistsPage() {
  const [spotify, setSpotify] = useState<SpotifyStatus | null>(null);
  const [available, setAvailable] = useState<SpotifyPlaylistRef[] | null>(null);
  const [imported, setImported] = useState<Playlist[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [gaps, setGaps] = useState<Record<number, GapAnalysis>>({});
  const [manualName, setManualName] = useState("");
  const [manualText, setManualText] = useState("");

  const reload = useCallback(() => {
    listImportedPlaylists().then(setImported).catch((e) => setError(err(e)));
  }, []);

  useEffect(() => {
    apiGet<SpotifyStatus>("/api/spotify/status").then(setSpotify).catch((e) => setError(err(e)));
    reload();
  }, [reload]);

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
    setNotice(null);
    setBusy(playlistId);
    try {
      const rep = await importPlaylist(playlistId);
      setNotice(`Importata "${rep.name}": ${rep.created} nuove, ${rep.updated} aggiornate, ${rep.skipped} saltate.`);
      reload();
    } catch (e) {
      setError(`Import di ${label} fallito: ${err(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const doManualImport = async () => {
    setError(null);
    setNotice(null);
    setBusy("manual");
    try {
      const rep = await importManualPlaylist(manualName.trim() || "Playlist manuale", manualText);
      setNotice(`Importata "${rep.name}": ${rep.created} nuove, ${rep.updated} riusate, ${rep.skipped} saltate.`);
      setManualName("");
      setManualText("");
      reload();
    } catch (e) {
      setError(`Import manuale fallito: ${err(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const loadGaps = async (id: number) => {
    setBusy(`gaps-${id}`);
    try {
      const result = await playlistGaps(id);
      setGaps((g) => ({ ...g, [id]: result }));
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(null);
    }
  };

  const connected = spotify?.configured && spotify?.user_connected;

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Playlist</h1>
        <p className="mt-1 text-sm text-muted">
          Importa una playlist Spotify come punto di partenza del tuo set.
        </p>
      </header>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}
      {notice && <div className="mb-4"><Alert tone="success">{notice}</Alert></div>}

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

      {/* Playlist disponibili su Spotify */}
      {connected && (
        <Card className="mb-6">
          <CardHeader
            title="Da Spotify"
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

      {/* Import manuale (testo / CSV) */}
      <Card className="mb-6">
        <CardHeader
          title="Import manuale"
          subtitle="Incolla una tracklist: una riga per traccia, formato “Artista - Titolo” (o CSV “artista,titolo”)."
        />
        <div className="grid gap-3 p-4">
          <Field label="Nome playlist">
            <Input
              value={manualName}
              onChange={(e) => setManualName(e.target.value)}
              placeholder="Es. Crate digging giugno"
              disabled={busy !== null}
            />
          </Field>
          <Field label="Tracklist" hint="Le tracce entrano senza BPM/key: arricchiscile poi da Impostazioni.">
            <Textarea
              value={manualText}
              onChange={(e) => setManualText(e.target.value)}
              rows={6}
              placeholder={"Daft Punk - Da Funk\nBonobo - Kerala\nFour Tet - Baby"}
              disabled={busy !== null}
            />
          </Field>
          <div className="flex justify-end">
            <Button onClick={doManualImport} disabled={busy !== null || manualText.trim() === ""}>
              {busy === "manual" ? <Spinner /> : <ClipboardList size={15} />} Importa tracklist
            </Button>
          </div>
        </div>
      </Card>

      {/* Playlist importate */}
      <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted">Importate</h2>
      {imported && imported.length === 0 && (
        <EmptyState icon={<ListPlus size={28} />} title="Nessuna playlist importata">
          Importa la prima playlist per iniziare a costruire un set.
        </EmptyState>
      )}
      <div className="grid gap-3">
        {imported?.map((p) => (
          <Card key={p.id} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <Music2 size={16} className="text-primary" />
                  <h3 className="truncate font-medium">{p.name}</h3>
                  <Badge tone="neutral">{p.platform}</Badge>
                  {p.kind === "liked" && <Badge tone="info">liked</Badge>}
                </div>
                <div className="mt-1 text-xs text-faint">{p.track_count} tracce</div>
              </div>
              <Button size="sm" variant="ghost" onClick={() => loadGaps(p.id)} disabled={busy !== null}>
                {busy === `gaps-${p.id}` ? <Spinner /> : <AlertTriangle size={15} />} Analizza buchi
              </Button>
            </div>

            {gaps[p.id] && (
              <div className="mt-3 grid gap-2 border-t border-border pt-3">
                {gaps[p.id].gaps.length === 0 && (
                  <p className="text-sm text-success">Nessun problema rilevante: la playlist è abbastanza bilanciata.</p>
                )}
                {gaps[p.id].gaps.map((g) => (
                  <div key={g.gap_type} className="flex gap-2 text-sm">
                    {g.severity === "warning"
                      ? <AlertTriangle size={15} className="mt-0.5 shrink-0 text-warning" />
                      : <Info size={15} className="mt-0.5 shrink-0 text-info" />}
                    <div>
                      <span className="text-fg">{g.description}</span>{" "}
                      <span className="text-muted">{g.suggestion}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}
