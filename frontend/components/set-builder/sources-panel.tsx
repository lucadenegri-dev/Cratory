"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { apiGet, errText, type Playlist, type Source } from "@/lib/api";
import { Badge, Select } from "@/components/ui";
import { useT } from "@/lib/i18n";

type Props = {
  sources: Source[];
  onAdd: (playlistId: number) => void;
  onRemove: (playlistId: number) => void;
};

/** Le playlist da cui il set pesca. Si aggiungono e si tolgono mentre si
 *  lavora; toglierne una toglie le sue tracce dal materiale, **non** dal
 *  percorso — una traccia già scelta è una decisione presa. */
export function SourcesPanel({ sources, onAdd, onRemove }: Props) {
  const t = useT();
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [errore, setErrore] = useState<string | null>(null);

  useEffect(() => {
    apiGet<Playlist[]>("/api/playlists")
      .then(setPlaylists)
      .catch((e) => setErrore(errText(e)));
  }, []);

  const scelte = new Set(sources.map((s) => s.playlist_id));
  const disponibili = playlists.filter((p) => !scelte.has(p.id));

  return (
    <div data-testid="sources-panel" className="mb-3 border-b border-border pb-3">
      <div className="mb-1 text-xs uppercase tracking-wider text-muted">
        {t.sets.manual.sourcesTitle}
      </div>
      {sources.length === 0 && <p className="text-sm text-muted">{t.sets.manual.sourcesEmpty}</p>}
      <div className="flex flex-wrap gap-1.5">
        {sources.map((s) => (
          <span key={s.playlist_id} className="inline-flex items-center gap-1">
            <Badge>{s.name ?? `#${s.playlist_id}`}</Badge>
            <button type="button" title={t.sets.manual.removeSourceTitle}
              onClick={() => onRemove(s.playlist_id)} className="text-muted hover:text-danger">
              <X size={13} />
            </button>
          </span>
        ))}
      </div>
      {disponibili.length > 0 && (
        <Select className="mt-2 w-full text-xs" value=""
          aria-label={t.sets.manual.addSourceLabel}
          onChange={(e) => { if (e.target.value) onAdd(Number(e.target.value)); }}>
          <option value="">{t.sets.manual.addSourceLabel}</option>
          {disponibili.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </Select>
      )}
      {errore && <p className="mt-1 text-xs text-danger">⚠ {errore}</p>}
    </div>
  );
}
