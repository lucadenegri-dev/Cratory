"use client";

import { useState } from "react";
import { type ManualRow } from "@/lib/api";
import { Button, Input } from "@/components/ui";
import { useT } from "@/lib/i18n";

type Props = {
  row: ManualRow;
  onFill: (row: ManualRow, count: number) => void;
  onClose: () => void;
};

/** Il generatore come strumento: propone N tracce per questo varco. Le proposte
 *  entrano come righe normali, quindi si cambiano e si annullano come tutto. */
export function FillGapPanel({ row, onFill, onClose }: Props) {
  const t = useT();
  const [count, setCount] = useState(2);
  return (
    <div data-testid="fill-gap" className="my-1 flex flex-wrap items-end gap-2 bg-surface-2 p-2">
      <div>
        <label htmlFor="fill-count" className="block text-xs text-muted">
          {t.sets.manual.fillGapCountLabel}
        </label>
        <Input id="fill-count" type="number" min={1} max={10} className="tnum mt-1 w-20"
          value={count} onChange={(e) => setCount(Number(e.target.value))} />
      </div>
      <Button size="sm" variant="outline" onClick={() => onFill(row, count)}>
        {t.sets.manual.fillGapButton}
      </Button>
      <Button size="sm" variant="ghost" onClick={onClose}>{t.common.cancel}</Button>
    </div>
  );
}
