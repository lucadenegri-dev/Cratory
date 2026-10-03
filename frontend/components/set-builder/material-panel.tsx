"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp, Bookmark, Layers, Plus } from "lucide-react";
import { fmtDateShort, type Material, type MaterialItem } from "@/lib/api";
import { Badge, Chip, Input, Loading, Select } from "@/components/ui";
import { TrackPlayButton } from "@/components/track-play-button";
import { CAMELOT_KEYS } from "@/lib/camelot";
import { useT } from "@/lib/i18n";
import {
  defaultDir, filterMaterial, sortMaterial, type MaterialSort, type SortDir,
} from "@/lib/material-view";

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

/** Un campo numerico vuoto o illeggibile non filtra. */
const bound = (v: string) => (v.trim() === "" || Number.isNaN(Number(v)) ? null : Number(v));

/** Pannello Materiale: playlist aggiornata + ricerca; il tasto + manda la
 *  traccia in coda al percorso. Le tracce gia' nel set restano visibili.
 *  Ordinamento e filtri BPM/tonalita' vivono qui e lavorano sul materiale gia'
 *  caricato: niente richiesta al backend a ogni tasto. */
export function MaterialPanel({
  material, query, owned, unused, onQuery, onOwned, onUnused, onAdd,
  onReserve, onAddAlternative, reserved, onReserved, canAddAlternative,
}: Props) {
  const t = useT();
  const [sort, setSort] = useState<MaterialSort>("playlist");
  const [dir, setDir] = useState<SortDir>("asc");
  const [bpmMin, setBpmMin] = useState("");
  const [bpmMax, setBpmMax] = useState("");
  const [key, setKey] = useState("");
  const visible = useMemo(() => {
    const items = material?.items ?? [];
    const kept = filterMaterial(items, { bpmMin: bound(bpmMin), bpmMax: bound(bpmMax), key: key || null });
    return sortMaterial(kept, sort, dir);
  }, [material, sort, dir, bpmMin, bpmMax, key]);
  // Il player scorre avanti e indietro nell'ordine che si vede.
  const playable = visible.filter((it) => it.track.has_local_file).map((it) => it.track);
  const total = material?.items.length ?? 0;

  // Il chip attivo, ricliccato, gira il verso; «playlist» non ne ha uno.
  const onSort = (next: MaterialSort) => {
    if (next === sort) {
      if (next !== "playlist") setDir(dir === "asc" ? "desc" : "asc");
      return;
    }
    setSort(next);
    setDir(defaultDir(next));
  };
  const sorts: [MaterialSort, string][] = [
    ["playlist", t.sets.manual.sortPlaylist], ["key", t.sets.manual.sortKey],
    ["bpm", t.sets.manual.sortBpm], ["added", t.sets.manual.sortAdded],
  ];
  return (
    <div className="flex h-full flex-col gap-3" data-testid="material-panel">
      <Input value={query} onChange={(e) => onQuery(e.target.value)} placeholder={t.sets.manual.searchPlaceholder} />
      <div className="flex flex-wrap gap-2">
        <Chip on={owned} onClick={() => onOwned(!owned)}>{t.sets.manual.filterOwned}</Chip>
        <Chip on={unused} onClick={() => onUnused(!unused)}>{t.sets.manual.filterUnused}</Chip>
        <Chip on={reserved} onClick={() => onReserved(!reserved)}>{t.sets.manual.filterReserved}</Chip>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-medium uppercase tracking-wider text-muted">{t.sets.manual.sortLabel}</span>
        {sorts.map(([value, label]) => (
          <Chip key={value} on={sort === value} onClick={() => onSort(value)}>
            <span className="inline-flex items-center gap-1">
              {label}
              {sort === value && value !== "playlist" && (dir === "asc"
                ? <ArrowUp size={11} aria-hidden /> : <ArrowDown size={11} aria-hidden />)}
            </span>
          </Chip>
        ))}
      </div>
      {/* Due righe e non una: la colonna del materiale e' la piu' stretta della
          pagina, e tre campi affiancati non ci stanno. */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <Input type="number" inputMode="decimal" min={0} className="h-8 min-w-0 flex-1 px-2 tnum"
            value={bpmMin} onChange={(e) => setBpmMin(e.target.value)} placeholder={t.sets.manual.filterBpmMin} />
          <span className="text-faint" aria-hidden>–</span>
          <Input type="number" inputMode="decimal" min={0} className="h-8 min-w-0 flex-1 px-2 tnum"
            value={bpmMax} onChange={(e) => setBpmMax(e.target.value)} placeholder={t.sets.manual.filterBpmMax} />
        </div>
        <Select className="h-8" aria-label={t.sets.manual.filterKeyLabel} value={key}
          onChange={(e) => setKey(e.target.value)}>
          <option value="">{t.sets.manual.filterKeyAny}</option>
          {CAMELOT_KEYS.map((k) => <option key={k} value={k}>{k}</option>)}
        </Select>
      </div>
      {material === null && <Loading />}
      {material && total === 0 && (
        <p className="text-sm text-muted">{t.sets.manual.materialEmpty}</p>
      )}
      {total > 0 && visible.length === 0 && (
        <p className="text-sm text-muted">{t.sets.manual.materialNoMatch}</p>
      )}
      {visible.length > 0 && visible.length < total && (
        <p className="tnum text-xs text-muted">{t.sets.manual.materialShown(visible.length, total)}</p>
      )}
      <ul className="divide-y divide-border">
        {visible.map((it) => (
          <li key={it.track.id} className="flex items-center gap-2 py-2">
            <TrackPlayButton track={it.track} context={playable} />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm">{it.track.artist} – {it.track.title}</div>
              <div className="flex flex-wrap gap-x-2 text-xs text-muted">
                <span className="tnum">{it.track.bpm ?? t.sets.manual.unknownValue}</span>
                <span>{it.track.camelot_key ?? t.sets.manual.unknownValue}</span>
                {/* Il genere e' l'unico dato di lunghezza libera in questa riga, e
                    la colonna e' la piu' stretta delle tre: senza un tetto
                    manderebbe le pastiglie a capo da solo. */}
                {it.track.genre && <span className="max-w-28 truncate">{it.track.genre}</span>}
                {sort === "added" && it.playlist_added_at && (
                  <span className="tnum" title={t.sets.manual.addedTitle}>{fmtDateShort(it.playlist_added_at)}</span>
                )}
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
