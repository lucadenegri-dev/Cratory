"use client";

import { useState } from "react";
import { FolderOpen, Link2, Search } from "lucide-react";
import { Alert, Button, Input, Loading, Modal, Spinner } from "@/components/ui";
import {
  errText, fmtSize, linkLocalFile, searchLocalFiles,
  type LocalFileHit, type TrackDetail,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { PathPickerButton, usePickerAvailability } from "@/components/path-picker-button";
import { sourceLabel } from "@/lib/track-source";

export type LinkTarget = { id: number; artist: string | null; title: string | null };

/** Wrapper: monta il dialog solo con un target e lo rigenera per ogni traccia. */
export function LinkLocalFileModal({ target, onClose, onLinked }: {
  target: LinkTarget | null;
  onClose: () => void;
  onLinked: (track: TrackDetail) => void;
}) {
  if (!target) return null;
  return <LinkDialog key={target.id} target={target} onClose={onClose} onLinked={onLinked} />;
}

/** Modal "Collega file locale": ricerca per nome sul disco + percorso esatto. */
function LinkDialog({ target, onClose, onLinked }: {
  target: LinkTarget;
  onClose: () => void;
  onLinked: (track: TrackDetail) => void;
}) {
  const t = useT();
  const SOURCE_LABEL = sourceLabel(t);
  // Precompilata con "artista titolo": di solito basta per trovare il file.
  const [query, setQuery] = useState(() =>
    `${target.artist ?? ""} ${target.title ?? ""}`.trim());
  const [hits, setHits] = useState<LocalFileHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [manualPath, setManualPath] = useState("");
  const [linking, setLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pickerOk = usePickerAvailability();

  const runSearch = async () => {
    const q = query.trim();
    if (q.length < 2) return;
    setSearching(true);
    setError(null);
    try {
      setHits(await searchLocalFiles(q));
    } catch (e) {
      setError(errText(e));
    } finally {
      setSearching(false);
    }
  };

  const link = async (path: string) => {
    setLinking(true);
    setError(null);
    try {
      const track = await linkLocalFile(target.id, path);
      onLinked(track);
      onClose();
    } catch (e) {
      // 400 tipico: file inesistente o estensione non audio.
      setError(errText(e));
    } finally {
      setLinking(false);
    }
  };

  return (
    <Modal open onClose={onClose} title={t.tracks.linkFileTitle} size="lg">
      <div className="space-y-4 p-4">
        <p className="text-sm text-muted">{target.artist ?? "?"} — {target.title ?? "?"}</p>
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        <form
          className="flex items-center gap-2"
          onSubmit={(e) => { e.preventDefault(); runSearch(); }}
        >
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t.tracks.searchByNamePlaceholder}
          />
          <Button type="submit" variant="outline"
            disabled={searching || query.trim().length < 2}>
            <Search size={14} /> {t.common.search}
          </Button>
        </form>
        {searching && <Loading label={t.tracks.searchingDiskShort} />}
        {hits && hits.length === 0 && !searching && (
          <p className="text-sm text-faint">
            {t.tracks.noFileFound}
          </p>
        )}
        {hits && hits.length > 0 && (
          <ul className="max-h-64 divide-y divide-border overflow-y-auto border border-border">
            {hits.map((h) => (
              <li key={h.path} className="flex items-center gap-3 px-3 py-2 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-xs">{h.name}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    <FolderOpen size={11} className="mr-1 inline" />
                    {SOURCE_LABEL[h.source] ?? h.source}
                    {h.format ? ` · ${h.format.toUpperCase()}` : ""}
                    {h.size ? ` · ${fmtSize(h.size)}` : ""}
                  </div>
                </div>
                <Button type="button" size="sm" onClick={() => link(h.path)} disabled={linking}>
                  {linking ? <Spinner /> : <Link2 size={13} />} {t.tracks.linkAction}
                </Button>
              </li>
            ))}
          </ul>
        )}

        <form
          className="border-t border-border pt-3"
          onSubmit={(e) => { e.preventDefault(); link(manualPath.trim()); }}
        >
          <div className="mb-1.5 text-[10px] uppercase tracking-wider text-muted">
            {t.tracks.exactPathLabel}
          </div>
          <div className="flex items-center gap-2">
            <Input
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              placeholder={t.tracks.exactPathPlaceholder}
            />
            {pickerOk && (
              <PathPickerButton kind="file" prompt={t.tracks.exactPathLabel}
                onPick={setManualPath} onError={setError} />
            )}
            <Button type="submit" variant="outline"
              disabled={linking || !manualPath.trim()}>
              <Link2 size={14} /> {t.tracks.linkAction}
            </Button>
          </div>
        </form>
      </div>
    </Modal>
  );
}
