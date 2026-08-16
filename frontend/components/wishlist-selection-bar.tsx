"use client";

import { Download as DownloadIcon } from "lucide-react";
import { Button } from "@/components/ui";
import { useT } from "@/lib/i18n";

export type SelectionBarProps = {
  count: number;
  onEnqueue: () => void;
  onClear: () => void;
  busy: boolean;
  /** slskd configurato? Senza, quelle tracce non partirebbero mai e il backend
   *  risponde 409: meglio un bottone spento che una richiesta rifiutata.
   *  Distinto da `busy`, che è "sto già accodando". */
  canEnqueue?: boolean;
};

/** Barra di selezione multipla: appare sopra la lista wishlist solo quando
 *  almeno una riga e' selezionata (vedi app/wishlist/page.tsx). */
export function SelectionBar({ count, onEnqueue, onClear, busy, canEnqueue = true }: SelectionBarProps) {
  const t = useT();
  if (count === 0) return null;
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border border-border-strong bg-elevated px-4 py-2.5 text-sm">
      {/* role="status" (=> aria-live="polite" implicito, ridondato esplicitamente
          per coerenza col resto del repo) annuncia il conteggio a chi usa uno
          screen reader senza cambiare l'aspetto visivo. */}
      <span className="text-fg-strong" role="status" aria-live="polite">{t.wishlist.selectedCount(count)}</span>
      <span className="flex flex-wrap items-center gap-2">
        <Button size="sm" variant="outline" onClick={onClear}>{t.wishlist.clearSelection}</Button>
        <Button size="sm" disabled={busy || !canEnqueue} onClick={onEnqueue}>
          <DownloadIcon size={13} /> {t.wishlist.enqueueSelected(count)}
        </Button>
      </span>
    </div>
  );
}
