"use client";

import { useState } from "react";
import { fileThumbUrl } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

export type CoverSource = "embedded" | "provider" | null;

/** Miniatura quadrata della traccia, condivisa da FILES, ISSUES, DUPLICATES e PLAN.
 *
 * `source` arriva solo da FILES (l'unica lista che lo espone): quando è `null` si
 * disegna il placeholder senza nemmeno fare la richiesta, quando è `"provider"` la
 * copertina è tratteggiata perché è una proposta, non ciò che c'è nel file.
 * Nelle altre liste si omette e si ricade sul placeholder via `onError`. */
export function CoverThumb({ fileId, size = 32, source }: {
  fileId: number;
  size?: number;
  source?: CoverSource;
}) {
  const t = useT();
  const [failed, setFailed] = useState(false);
  const box = { width: size, height: size };

  if (source === null || failed) {
    return <span aria-hidden className="cv-none block shrink-0 border border-border" style={box} />;
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={fileThumbUrl(fileId)}
      alt={t.common.coverAlt}
      title={source === "provider" ? t.common.coverProposed : undefined}
      width={size}
      height={size}
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
      style={box}
      className={cn("block shrink-0 border border-border object-cover",
        source === "provider" && "border-dashed opacity-50")}
    />
  );
}
