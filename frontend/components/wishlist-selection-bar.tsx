"use client";

import { Download as DownloadIcon } from "lucide-react";
import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";

export type SelectionBarProps = {
  count: number;
  onEnqueue: () => void;
  onClear: () => void;
  busy: boolean;
};

/** Barra di selezione multipla: appare sopra la lista wishlist solo quando
 *  almeno una riga e' selezionata (vedi app/wishlist/page.tsx). */
export function SelectionBar({ count, onEnqueue, onClear, busy }: SelectionBarProps) {
  const t = useT();
  if (count === 0) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border border-border-strong bg-elevated px-4 py-2.5 text-sm">
      <span className="text-fg-strong">{t.wishlist.selectedCount(count)}</span>
      <span className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" onClick={onClear}>{t.wishlist.clearSelection}</Button>
        <Button size="sm" disabled={busy} onClick={onEnqueue}>
          <DownloadIcon size={13} /> {t.wishlist.enqueueSelected(count)}
        </Button>
      </span>
    </div>
  );
}
