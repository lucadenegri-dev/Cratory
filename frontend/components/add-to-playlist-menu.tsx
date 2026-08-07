"use client";

import { useEffect, useRef, useState } from "react";
import { Check, ListPlus, Plus } from "lucide-react";
import { addTracksToPlaylist, createPlaylistFromTracks, errText, listImportedPlaylists, type Playlist } from "@/lib/api";
import { Button, Input, Spinner } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** Popover "aggiungi a playlist": aggiunge una o più tracce a una playlist
 *  manuale esistente, o ne crea una nuova. Con una sola traccia marca le
 *  playlist che la contengono già (`inPlaylistIds`); `excludePlaylistId`
 *  nasconde la playlist corrente (es. barra bulk del dettaglio playlist). */
export function AddToPlaylistMenu({ trackIds, inPlaylistIds = [], excludePlaylistId, onChanged }: {
  trackIds: number[];
  inPlaylistIds?: number[];
  excludePlaylistId?: number;
  onChanged: () => void;
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [busy, setBusy] = useState<number | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSuccess(null);
    setError(null);
    setCreating(false);
    setNewName("");
    listImportedPlaylists()
      .then((all) => setPlaylists(all.filter((p) => p.kind === "manual" && p.id !== excludePlaylistId)))
      .catch(() => setPlaylists([]));
  }, [open, excludePlaylistId]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  // "Già presente" ha senso solo per una singola traccia (dettaglio traccia).
  const inIds = new Set(trackIds.length === 1 ? inPlaylistIds : []);

  const addTo = async (pl: Playlist) => {
    setBusy(pl.id);
    setError(null);
    setSuccess(null);
    try {
      await addTracksToPlaylist(pl.id, trackIds);
      onChanged();
      setSuccess(t.tracks.addedToPlaylist(pl.name));
    } catch (e) {
      setError(t.tracks.addToPlaylistFailed(errText(e)));
    } finally {
      setBusy(null);
    }
  };

  const createAndAdd = async () => {
    if (!newName.trim()) return;
    setBusy("new");
    setError(null);
    setSuccess(null);
    try {
      const created = await createPlaylistFromTracks(newName.trim(), trackIds);
      setPlaylists((prev) => [...prev, created]);
      onChanged();
      setSuccess(t.tracks.createdPlaylist(newName.trim()));
      setNewName("");
      setCreating(false);
    } catch (e) {
      setError(t.tracks.addToPlaylistFailed(errText(e)));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div ref={ref} className="relative">
      <Button size="sm" variant="outline" onClick={() => setOpen((o) => !o)}>
        <ListPlus size={14} /> {t.tracks.addToPlaylist}
      </Button>
      {open && (
        <div className="absolute left-0 z-20 mt-1 w-64 border border-border bg-elevated p-1 shadow-lg">
          {error && <p className="px-2 py-1 text-xs text-danger">⚠ {error}</p>}
          {success && <p className="px-2 py-1 text-xs text-fg">{success}</p>}
          <div className="max-h-60 overflow-y-auto">
            {playlists.length === 0 && (
              <p className="px-2 py-3 text-center text-xs text-muted">{t.tracks.addToPlaylistNoManual}</p>
            )}
            {playlists.map((pl) => {
              const already = inIds.has(pl.id);
              return (
                <button
                  key={pl.id}
                  type="button"
                  disabled={already || busy !== null}
                  onClick={() => addTo(pl)}
                  className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-sm hover:bg-surface disabled:cursor-default disabled:opacity-60"
                >
                  <span className="min-w-0 flex-1 truncate">{pl.name}</span>
                  {busy === pl.id ? <Spinner /> : already ? <Check size={14} className="text-fg" /> : <Plus size={14} className="text-muted" />}
                </button>
              );
            })}
          </div>
          <div className="mt-1 border-t border-border pt-1">
            {creating ? (
              <div className="flex items-center gap-1 p-1">
                <Input
                  className="h-8 flex-1"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  placeholder={t.tracks.newPlaylistNamePlaceholder}
                  autoFocus
                />
                <Button size="sm" onClick={createAndAdd} disabled={busy !== null || !newName.trim()}>
                  {busy === "new" ? <Spinner /> : t.tracks.createAndAddButton}
                </Button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setCreating(true)}
                className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-sm text-muted hover:bg-surface hover:text-fg"
              >
                <Plus size={14} /> {t.tracks.createNewPlaylistOption}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
