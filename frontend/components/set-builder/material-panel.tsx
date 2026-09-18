"use client";

import { Bookmark, Layers, Plus } from "lucide-react";
import { type Material, type MaterialItem } from "@/lib/api";
import { Badge, Chip, Input, Loading } from "@/components/ui";
import { TrackPlayButton } from "@/components/track-play-button";
import { useT } from "@/lib/i18n";

type Props = {
  material: Material | null;
  query: string;
  owned: boolean;
  unused: boolean;
  onQuery: (q: string) => void;
  onOwned: (v: boolean) => void;
  onUnused: (v: boolean) => void;
  onAdd: (item: MaterialItem) => void;
  onReserve: (item: MaterialItem) => void;
  onAddAlternative: (item: MaterialItem) => void;
  reserved: boolean;
  onReserved: (v: boolean) => void;
  /** Vero solo con una riga selezionata: senza, «tieni come alternativa» non
   *  avrebbe un punto a cui attaccare la candidata. */
  canAddAlternative: boolean;
};

/** Pannello Materiale: playlist aggiornata + ricerca; il tasto + manda la
 *  traccia in coda al percorso. Le tracce gia' nel set restano visibili. */
export function MaterialPanel({
  material, query, owned, unused, onQuery, onOwned, onUnused, onAdd,
  onReserve, onAddAlternative, reserved, onReserved, canAddAlternative,
}: Props) {
  const t = useT();
  const playable = material?.items.filter((it) => it.track.has_local_file).map((it) => it.track) ?? [];
  return (
    <div className="flex h-full flex-col gap-3" data-testid="material-panel">
      <Input value={query} onChange={(e) => onQuery(e.target.value)} placeholder={t.sets.manual.searchPlaceholder} />
      <div className="flex flex-wrap gap-2">
        <Chip on={owned} onClick={() => onOwned(!owned)}>{t.sets.manual.filterOwned}</Chip>
        <Chip on={unused} onClick={() => onUnused(!unused)}>{t.sets.manual.filterUnused}</Chip>
        <Chip on={reserved} onClick={() => onReserved(!reserved)}>{t.sets.manual.filterReserved}</Chip>
      </div>
      {material === null && <Loading />}
      {material && material.items.length === 0 && (
        <p className="text-sm text-muted">{t.sets.manual.materialEmpty}</p>
      )}
      <ul className="divide-y divide-border">
        {material?.items.map((it) => (
          <li key={it.track.id} className="flex items-center gap-2 py-2">
            <TrackPlayButton track={it.track} context={playable} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm">{it.track.artist} – {it.track.title}</div>
              <div className="flex flex-wrap gap-x-2 text-xs text-muted">
                <span className="tnum">{it.track.bpm ?? t.sets.manual.unknownValue}</span>
                <span>{it.track.camelot_key ?? t.sets.manual.unknownValue}</span>
                {!it.track.has_local_file && <Badge tone="warning">{t.sets.manual.noFileBadge}</Badge>}
                {it.in_set && <Badge>{t.sets.manual.inSetBadge}</Badge>}
              </div>
            </div>
            {!it.in_set && (
              <button type="button" title={t.sets.manual.addTitle} onClick={() => onAdd(it)}
                className="grid h-7 w-7 place-items-center border border-border text-muted hover:text-fg">
                <Plus size={14} />
              </button>
            )}
            {!it.in_reserve && (
              <button type="button" title={t.sets.manual.reserveAddTitle} onClick={() => onReserve(it)}
                className="grid h-7 w-7 place-items-center border border-border text-muted hover:text-fg">
                <Bookmark size={14} />
              </button>
            )}
            {canAddAlternative && (
              <button type="button" title={t.sets.manual.addAlternativeTitle} onClick={() => onAddAlternative(it)}
                className="grid h-7 w-7 place-items-center border border-border text-muted hover:text-fg">
                <Layers size={14} />
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
