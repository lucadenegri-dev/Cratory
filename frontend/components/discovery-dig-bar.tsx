"use client";

import { useMemo } from "react";
import { Disc3, Shovel, Tags } from "lucide-react";

import { Button, Combobox, SegmentedControl, Select, Spinner, type ComboOption } from "@/components/ui";
import { useT } from "@/lib/i18n";

/** DOVE si pesca nella pila ordinata per domanda. Non e' un mix di ordinamento:
 *  sceglie il bacino (vedi spec del motore, `_window`). */
export const DEPTHS = [
  { key: "surface", value: 0.0 },
  { key: "mid", value: 0.5 },
  { key: "deep", value: 1.0 },
] as const;

export type SeedType = "genre" | "label";

export function DiscoveryDigBar({
  subject, onSubjectChange, depth, onDepthChange, tasteRef, onTasteRefChange,
  options, pilePages, busy, ready, onSubmit,
}: {
  subject: string;
  onSubjectChange: (value: string, seed: SeedType) => void;
  depth: number;
  onDepthChange: (v: number) => void;
  tasteRef: number | null;
  onTasteRefChange: (v: number | null) => void;
  options: {
    genres: { library: string[]; styles: string[] };
    labels: string[];
    playlists: { id: number; name: string }[];
  };
  pilePages: number | null;
  busy: boolean;
  ready: boolean;
  onSubmit: () => void;
}) {
  const t = useT();

  // Ordine a campo vuoto voluto dalla spec: generi di libreria, poi etichette, poi gli
  // style curati (il "resto" che la libreria non ha — il mestiere di Discovery). Un
  // genere puo' comparire sia in `library` sia in `styles`: dedup globale case-insensitive,
  // la libreria vince (mantiene la grafia che l'utente si e' scelto). Il Combobox non
  // riordina, riceve gia' l'ordine giusto.
  const comboOptions: ComboOption[] = useMemo(() => {
    const seen = new Set<string>();
    const asGenreOptions = (list: string[]) =>
      list
        .filter((g) => {
          const key = g.trim().toLowerCase();
          if (!key || seen.has(key)) return false;
          seen.add(key);
          return true;
        })
        .map((g) => ({ value: g, label: g, group: t.discovery.groupGenre, icon: <Disc3 size={13} /> }));
    return [
      ...asGenreOptions(options.genres.library),
      ...options.labels.map((l) => ({
        value: l, label: l, group: t.discovery.groupLabel, icon: <Tags size={13} />,
      })),
      ...asGenreOptions(options.genres.styles),
    ];
  }, [options.genres, options.labels, t]);

  const depthOptions = DEPTHS.map((d) => ({
    value: String(d.value),
    label: t.discovery[d.key === "surface" ? "depthSurface" : d.key === "mid" ? "depthMid" : "depthDeep"],
  }));
  const activeDepth = DEPTHS.reduce((best, d) =>
    Math.abs(d.value - depth) < Math.abs(best.value - depth) ? d : best, DEPTHS[0]);
  const depthDesc = t.discovery[
    activeDepth.key === "surface" ? "depthSurfaceDesc"
      : activeDepth.key === "mid" ? "depthMidDesc" : "depthDeepDesc"
  ];

  // Due casi diversi, non uno. La pila NON ESISTE (seme che Discogs non conosce) e' altra
  // cosa da una pila CORTA (seme vero ma con pochi dischi): confonderli fa dire alla UI
  // "tutta qui" su un seme che non ha mai avuto niente. In entrambi i casi `depth` non ha
  // effetto e il controllo va spento, ma il motivo va detto giusto.
  const emptyPile = pilePages === 0;
  const shortPile = pilePages !== null && pilePages > 0 && pilePages <= 3;
  const depthInert = emptyPile || shortPile;

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
      className="mb-6 border border-border p-4"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        {/* Zona soggetto: niente microlabel ridondante — placeholder e gruppi
            (genere/etichetta) nel menu bastano a spiegarla; "Scava" resta solo
            sull'azione, non anche qui appesa a fianco del campo. */}
        <div className="min-w-[240px] flex-1">
          <Combobox
            value={subject}
            options={comboOptions}
            disabled={busy}
            placeholder={t.discovery.subjectPlaceholder}
            onChange={(v) => onSubjectChange(v, "genre")}
            onSelect={(o) => onSubjectChange(o.value, o.group === t.discovery.groupLabel ? "label" : "genre")}
          />
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.depthLabel}</span>
          <SegmentedControl
            value={String(activeDepth.value)}
            onChange={(v) => onDepthChange(Number(v))}
            options={depthOptions}
            disabled={busy || depthInert}
          />
        </div>

        {options.playlists.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.affinityLabel}</span>
            <div className="w-[220px]">
              <Select
                value={tasteRef ?? ""}
                disabled={busy}
                onChange={(e) => onTasteRefChange(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">{t.discovery.wholeLibraryOption}</option>
                {options.playlists.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </Select>
            </div>
          </div>
        )}

        <Button type="submit" disabled={busy || !ready} className="w-full sm:w-auto">
          {busy ? <Spinner /> : <Shovel size={15} />} {t.discovery.dig}
        </Button>
      </div>

      <p className="mt-2 text-xs text-muted">
        {emptyPile ? t.discovery.emptyPile : shortPile ? t.discovery.shortPile : depthDesc}
      </p>
      {options.playlists.length > 0 && (
        // Onestà del microcopy (spec): il gusto non filtra, sceglie solo il riferimento
        // per l'affinità — i dischi gia' posseduti restano esclusi comunque. Sotto il
        // controllo, come il microcopy della profondità: non c'e' spazio in riga per
        // una frase intera senza rompere la riga singola su desktop.
        <p className="mt-1 text-xs text-muted">{t.discovery.affinityHint}</p>
      )}
    </form>
  );
}
