"use client";

import { useEffect, useMemo, useState } from "react";
import { Disc3, Tags, X } from "lucide-react";

import { Chip, Combobox, type ComboOption } from "@/components/ui";
import { useT } from "@/lib/i18n";
import type { GenreCount } from "@/lib/api/types";
import { addSeed, MAX_SEEDS, removeSeed, seedKey, type DigSeed } from "@/lib/discovery-seeds";
import { cn } from "@/lib/cn";

const FLASH_MS = 600;

/* I semi scelti come chip, un campo per aggiungerne (dal menu o a mano) e una
   tavolozza di quello che c'è già: la cura per "la selezione è scomoda" è
   vedere cosa si ha PRIMA di digitare. Il Combobox resta quello del DS: il
   testo libero confermato con Invio è un genere, come prima. */
export function DiscoverySeedPicker({ seeds, onChange, options, disabled }: {
  seeds: DigSeed[];
  onChange: (seeds: DigSeed[]) => void;
  options: {
    genres: { library: string[]; styles: string[] };
    labels: string[];
    genreCounts: GenreCount[];
  };
  disabled?: boolean;
}) {
  const t = useT();
  const [text, setText] = useState("");
  const [flash, setFlash] = useState<string | null>(null);
  // Aperta a barra vuota, chiusa col primo seme: chi ha già scelto vuole i
  // risultati, non la tavolozza. Ma si riapre, e resta come la si è messa.
  const [paletteOpen, setPaletteOpen] = useState(seeds.length === 0);
  const full = seeds.length >= MAX_SEEDS;

  useEffect(() => {
    if (flash === null) return;
    const id = window.setTimeout(() => setFlash(null), FLASH_MS);
    return () => window.clearTimeout(id);
  }, [flash]);

  const add = (seed: DigSeed) => {
    const r = addSeed(seeds, seed);
    if (r.duplicate) { setFlash(seedKey(r.duplicate)); return; }
    if (r.full) return;
    onChange(r.seeds);
    setText("");
    if (r.seeds.length === 1) setPaletteOpen(false);
  };

  const toggle = (seed: DigSeed) => {
    const key = seedKey(seed);
    if (seeds.some((s) => seedKey(s) === key)) onChange(removeSeed(seeds, seed));
    else add(seed);
  };

  const isOn = (seed: DigSeed) => seeds.some((s) => seedKey(s) === seedKey(seed));

  // Stesso ordine e stessa dedup di prima: libreria, etichette, stili curati;
  // un genere presente in entrambe le liste compare una volta, con la grafia
  // della libreria. In più: chi è già un seme non ricompare nel menu — non ha
  // senso riproporlo, e il Combobox si apre già digitando (non solo a fuoco),
  // quindi un seme già scelto ci finirebbe dentro anche solo a ridigitarne il nome.
  const comboOptions: ComboOption[] = useMemo(() => {
    const seen = new Set<string>();
    const genres = (list: string[]) => list
      .filter((g) => { const k = g.trim().toLowerCase(); if (!k || seen.has(k)) return false; seen.add(k); return true; })
      .filter((g) => !isOn({ type: "genre", value: g }))
      .map((g) => ({ value: g, label: g, group: t.discovery.groupGenre, icon: <Disc3 size={13} /> }));
    const labels = options.labels
      .filter((l) => !isOn({ type: "label", value: l }))
      .map((l) => ({ value: l, label: l, group: t.discovery.groupLabel, icon: <Tags size={13} /> }));
    return [...genres(options.genres.library), ...labels, ...genres(options.genres.styles)];
    // eslint-disable-next-line react-hooks/exhaustive-deps -- isOn dipende solo da seeds, già in lista
  }, [options, t, seeds]);

  const libraryKeys = useMemo(
    () => new Set(options.genres.library.map((g) => g.trim().toLowerCase())), [options.genres.library]);
  const counts = useMemo(
    () => new Map(options.genreCounts.map((c) => [c.genre.trim().toLowerCase(), c.count])), [options.genreCounts]);
  const styleChips = options.genres.styles.filter((s) => !libraryKeys.has(s.trim().toLowerCase()));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        {seeds.map((s) => {
          const key = seedKey(s);
          return (
            <span
              key={key}
              data-flash={flash === key ? "" : undefined}
              className={cn(
                "inline-flex items-center gap-1.5 border border-border-strong bg-elevated px-2 py-1 text-xs text-fg",
                flash === key && "animate-pulse",
              )}
            >
              {s.type === "label" ? <Tags size={12} /> : <Disc3 size={12} />}
              {s.value}
              <button
                type="button"
                aria-label={t.discovery.removeSeed(s.value)}
                disabled={disabled}
                onClick={() => onChange(removeSeed(seeds, s))}
                className="ml-0.5 text-muted hover:text-fg disabled:opacity-50"
              >
                <X size={12} />
              </button>
            </span>
          );
        })}
        <div
          className="min-w-[240px] flex-1"
          // Il Combobox fa preventDefault solo quando SCEGLIE un'opzione: se
          // l'evento arriva qui intatto, Invio ha trovato solo testo libero.
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.defaultPrevented && text.trim()) {
              e.preventDefault();
              add({ type: "genre", value: text });
            }
          }}
        >
          <Combobox
            value={text}
            options={comboOptions}
            disabled={disabled || full}
            placeholder={full ? t.discovery.seedsFull(MAX_SEEDS) : t.discovery.seedsPlaceholder}
            onChange={setText}
            onSelect={(o) => add({ type: o.group === t.discovery.groupLabel ? "label" : "genre", value: o.value })}
          />
        </div>
      </div>
      {full && <p className="text-xs text-muted">{t.discovery.seedsFull(MAX_SEEDS)}</p>}

      <div className="border-t border-border pt-3">
        <button
          type="button"
          onClick={() => setPaletteOpen((v) => !v)}
          className="text-[10px] uppercase tracking-wider text-muted hover:text-fg"
        >
          {paletteOpen ? t.discovery.paletteHide : t.discovery.paletteShow}
        </button>
        {paletteOpen && (
          <div className="mt-2 flex flex-col gap-2">
            {options.genres.library.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-[10px] uppercase tracking-wider text-muted">{t.discovery.paletteLibrary}</span>
                {options.genres.library.map((g) => {
                  const n = counts.get(g.trim().toLowerCase());
                  return (
                    <Chip key={g} on={isOn({ type: "genre", value: g })} disabled={disabled}
                          onClick={() => toggle({ type: "genre", value: g })}>
                      {g}{n != null && <span className="tnum ml-1 text-faint">{n}</span>}
                    </Chip>
                  );
                })}
              </div>
            )}
            {styleChips.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="mr-1 text-[10px] uppercase tracking-wider text-muted">{t.discovery.paletteStyles}</span>
                {styleChips.map((s) => (
                  <Chip key={s} on={isOn({ type: "genre", value: s })} disabled={disabled}
                        onClick={() => toggle({ type: "genre", value: s })}>
                    {s}
                  </Chip>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
