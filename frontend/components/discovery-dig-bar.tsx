"use client";

import { Dices, Shovel } from "lucide-react";

import { Button, Checkbox, SegmentedControl, Spinner } from "@/components/ui";
import { DiscoverySeedPicker } from "@/components/discovery-seed-picker";
import { DiscoveryTrackSearch } from "@/components/discovery-track-search";
import { useI18n } from "@/lib/i18n";
import type { DiscoveryPile, GenreCount, Track } from "@/lib/api/types";
import { DEPTHS, WINDOW_ITEMS, type DigSourceKey } from "@/lib/discovery-dig";
import type { DigSeed } from "@/lib/discovery-seeds";

export type DigMode = "seeds" | "track";

/* Un riquadro, tre righe: i controlli del modo, il soggetto (semi o traccia),
   la tavolozza. Il modo è stato locale della pagina, non URL: commutarlo cambia
   solo quale campo si vede. In modo traccia sorgente e profondità lasciano il
   posto all'interruttore stile/periodo (i simili sono solo Bandcamp). */
export function DiscoveryDigBar({
  mode, onModeChange, seeds, onSeedsChange, depth, onDepthChange,
  source, onSourceChange, discogsEnabled, stylePeriod, onStylePeriodChange,
  options, piles, busy, onSubmit, onSurprise, canSurprise, onPickTrack, searchTracks,
}: {
  mode: DigMode;
  onModeChange: (m: DigMode) => void;
  seeds: DigSeed[];
  onSeedsChange: (s: DigSeed[]) => void;
  depth: number;
  onDepthChange: (v: number) => void;
  source: DigSourceKey;
  onSourceChange: (s: DigSourceKey) => void;
  discogsEnabled: boolean;
  stylePeriod: boolean;
  onStylePeriodChange: (v: boolean) => void;
  options: {
    genres: { library: string[]; styles: string[] };
    labels: string[];
    genreCounts: GenreCount[];
  };
  piles: DiscoveryPile[] | null;
  busy: boolean;
  onSubmit: () => void;
  onSurprise: () => void;
  canSurprise: boolean;
  onPickTrack: (t: Track) => void;
  searchTracks: (q: string) => Promise<Track[]>;
}) {
  const { t } = useI18n();
  const srcName = source === "bandcamp" ? t.discovery.sourceBandcamp : t.discovery.sourceDiscogs;

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

  // La soglia di "pila corta" è la quota di finestra di QUESTO scavo (300 diviso
  // i semi), non 300: con due semi una pila da 200 non è corta.
  const budget = Math.floor(WINDOW_ITEMS / Math.max(1, seeds.length));
  const live = piles?.filter((p) => p.total > 0) ?? [];
  const dead = piles?.filter((p) => p.total === 0) ?? [];
  const emptyPile = piles != null && piles.length > 0 && live.length === 0;
  const shortPile = live.length > 0 && live.every((p) => p.reach <= budget);
  const depthInert = emptyPile || shortPile;

  const hint = emptyPile
    ? t.discovery.emptyPile(srcName, piles?.length ?? 0)
    : shortPile
      ? t.discovery.shortPile
      : dead.length > 0
        ? t.discovery.deadSeeds(dead.map((p) => `“${p.value}”`).join(", "), srcName)
        : depthDesc;

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); if (mode === "seeds") onSubmit(); }}
      className="mb-6 border border-border p-4"
    >
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex items-center gap-2">
          <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.modeLabel}</span>
          <SegmentedControl<DigMode>
            value={mode}
            onChange={onModeChange}
            options={[
              { value: "seeds", label: t.discovery.modeSeeds },
              { value: "track", label: t.discovery.modeTrack },
            ]}
            disabled={busy}
          />
        </div>

        {mode === "seeds" && discogsEnabled && (
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.sourceLabel}</span>
            <SegmentedControl
              value={source}
              onChange={onSourceChange}
              options={[
                { value: "discogs", label: t.discovery.sourceDiscogs },
                { value: "bandcamp", label: t.discovery.sourceBandcamp },
              ]}
              disabled={busy}
            />
          </div>
        )}

        {mode === "seeds" ? (
          <div className="flex items-center gap-2">
            <span className="text-[10px] uppercase tracking-wider text-muted">{t.discovery.depthLabel}</span>
            <SegmentedControl
              value={String(activeDepth.value)}
              onChange={(v) => onDepthChange(Number(v))}
              options={depthOptions}
              disabled={busy || depthInert}
            />
          </div>
        ) : (
          <Checkbox
            label={t.discovery.similarStylePeriod}
            checked={stylePeriod}
            onChange={onStylePeriodChange}
            disabled={busy}
          />
        )}
      </div>

      <div className="mt-4">
        {mode === "seeds" ? (
          <div className="flex flex-col gap-3">
            <DiscoverySeedPicker seeds={seeds} onChange={onSeedsChange} options={options} disabled={busy} />
            <div className="flex flex-wrap items-center gap-2">
              <Button type="submit" disabled={busy || seeds.length === 0} className="w-full sm:w-auto">
                {busy ? <Spinner /> : <Shovel size={15} />} {t.discovery.dig}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={onSurprise}
                disabled={busy || !canSurprise}
                title={canSurprise ? undefined : t.discovery.surpriseEmpty}
                className="w-full sm:w-auto"
              >
                <Dices size={15} /> {t.discovery.surprise}
              </Button>
              <p className="text-xs text-muted">{hint}</p>
            </div>
          </div>
        ) : (
          <DiscoveryTrackSearch search={searchTracks} onPick={onPickTrack} disabled={busy} />
        )}
      </div>
    </form>
  );
}
