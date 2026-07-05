"use client";

import { useState } from "react";
import { FolderOpen, Link2, Search } from "lucide-react";
import { Alert, Button, Input, Loading, Modal, Spinner } from "@/components/ui";
import {
  linkLocalFile, searchLocalFiles,
  type LocalFileHit, type TrackDetail,
} from "@/lib/api";

export type LinkTarget = { id: number; artist: string | null; title: string | null };

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

function fmtSize(bytes: number | null): string {
  if (!bytes) return "";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

const SOURCE_LABEL: Record<string, string> = {
  library: "libreria",
  downloads: "download",
};

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
  // Precompilata con "artista titolo": di solito basta per trovare il file.
  const [query, setQuery] = useState(() =>
    `${target.artist ?? ""} ${target.title ?? ""}`.trim());
  const [hits, setHits] = useState<LocalFileHit[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [manualPath, setManualPath] = useState("");
  const [linking, setLinking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runSearch = async () => {
    const q = query.trim();
    if (q.length < 2) return;
    setSearching(true);
    setError(null);
    try {
      setHits(await searchLocalFiles(q));
    } catch (e) {
      setError(err(e));
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
      setError(err(e));
    } finally {
      setLinking(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="Collega file locale" size="lg">
      <div className="space-y-4 p-4">
        <p className="text-sm text-muted">{target.artist ?? "?"} — {target.title ?? "?"}</p>
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        <div className="flex items-center gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") runSearch();
            }}
            placeholder="Cerca per nome file…"
          />
          <Button variant="outline" onClick={runSearch}
            disabled={searching || query.trim().length < 2}>
            <Search size={14} /> Cerca
          </Button>
        </div>
        {searching && <Loading label="Cerco sul disco…" />}
        {hits && hits.length === 0 && !searching && (
          <p className="text-sm text-faint">
            Nessun file trovato: prova con meno parole o incolla il percorso qui sotto.
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
                <Button size="sm" onClick={() => link(h.path)} disabled={linking}>
                  {linking ? <Spinner /> : <Link2 size={13} />} Collega
                </Button>
              </li>
            ))}
          </ul>
        )}

        <div className="border-t border-border pt-3">
          <div className="mb-1.5 text-[10px] uppercase tracking-wider text-muted">
            Percorso esatto
          </div>
          <div className="flex items-center gap-2">
            <Input
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              placeholder="/percorso/assoluto/del/file.mp3"
            />
            <Button variant="outline" onClick={() => link(manualPath.trim())}
              disabled={linking || !manualPath.trim()}>
              <Link2 size={14} /> Collega
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
