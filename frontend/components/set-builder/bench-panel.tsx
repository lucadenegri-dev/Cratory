"use client";

import { CornerUpLeft } from "lucide-react";
import { type ManualBlock } from "@/lib/api";
import { TrackPlayButton } from "@/components/track-play-button";
import { useT } from "@/lib/i18n";

type Props = {
  blocks: ManualBlock[];
  onToPath: (block: ManualBlock) => void;
};

/** Il banco: sequenze parcheggiate fuori dal percorso, per provare un'idea
 *  senza smontare il set. Non contano nella durata né nel conteggio. */
export function BenchPanel({ blocks, onToPath }: Props) {
  const t = useT();
  return (
    <div data-testid="bench-panel" className="mt-4 border-t border-border pt-3">
      <div className="mb-1 flex items-baseline justify-between">
        <span className="text-xs uppercase tracking-wider text-muted">{t.sets.manual.benchTitle}</span>
      </div>
      {blocks.length === 0 && <p className="text-sm text-muted">{t.sets.manual.benchEmpty}</p>}
      {blocks.map((block) => {
        const playable = block.rows.map((r) => r.track)
          .filter((tr): tr is NonNullable<typeof tr> => !!tr?.has_local_file);
        return (
          <div key={block.id} className="mt-2">
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1 truncate text-sm">
                {block.name ?? <span className="text-muted">{t.sets.manual.sequenceUnnamed}</span>}
              </span>
              <span className="text-xs text-muted">{t.sets.manual.sequenceMeta(block.rows.length)}</span>
              <button type="button" title={t.sets.manual.benchToPathTitle}
                onClick={() => onToPath(block)} className="text-muted hover:text-fg">
                <CornerUpLeft size={14} />
              </button>
            </div>
            <ul className="divide-y divide-border">
              {block.rows.map((row) => (
                <li key={row.id} className="flex items-center gap-2 py-1.5 pl-3">
                  {row.track && <TrackPlayButton track={row.track} context={playable} />}
                  <span className="min-w-0 flex-1 truncate text-sm">
                    {row.track?.artist} – {row.track?.title}
                  </span>
                  <span className="tnum hidden max-w-32 truncate text-xs text-muted xl:inline">
                    {row.track?.bpm ?? t.sets.manual.unknownValue}{" "}
                    · {row.track?.camelot_key ?? t.sets.manual.unknownValue}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
