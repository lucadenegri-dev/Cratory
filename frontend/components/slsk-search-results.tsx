"use client";

import { useState } from "react";
import { ChevronLeft, ChevronRight, Download as DownloadIcon } from "lucide-react";
import { Button } from "@/components/ui";
import type { DownloadCandidate } from "@/lib/api";
import { useT } from "@/lib/i18n";

const PAGE_SIZE = 40;

/** Risultati della ricerca Soulseek libera: conteggio totale e paginazione
 * client-side su TUTTI i risultati (prima si troncava a 40 senza dirlo). */
export function SlskSearchResults({ results, onGrab, running }: {
  results: DownloadCandidate[];
  onGrab: (c: DownloadCandidate) => void;
  running: boolean;
}) {
  const t = useT();
  const [page, setPage] = useState(0);
  // Nuova ricerca = nuova lista: si riparte dalla prima pagina. Pattern
  // "stato dal render precedente" (react.dev), niente setState negli effect.
  const [prevResults, setPrevResults] = useState(results);
  if (prevResults !== results) {
    setPrevResults(results);
    setPage(0);
  }

  const pages = Math.max(1, Math.ceil(results.length / PAGE_SIZE));
  const safePage = Math.min(page, pages - 1);
  const start = safePage * PAGE_SIZE;
  const visible = results.slice(start, start + PAGE_SIZE);

  return (
    <div className="mt-3">
      <div className="text-xs text-muted">{t.downloads.resultsCount(results.length)}</div>
      <ul className="mt-1 divide-y divide-border border border-border">
        {visible.map((c, i) => {
          const parts = c.filename.split(/[\\/]/);
          const basename = parts.pop();
          const dir = parts.join("/");
          return (
          <li key={`${c.username}-${start + i}`} className="flex items-center justify-between gap-3 px-3 py-2">
            <div className="min-w-0">
              <div className="truncate text-sm">{basename}</div>
              {/* Il path e' meta' del giudizio su un candidato (artista/release
                  nelle cartelle): visibile, troncato, per esteso al passaggio. */}
              {dir && <div className="truncate text-xs text-muted" title={c.filename}>{dir}</div>}
              <div className="text-xs text-faint">
                {c.format?.toUpperCase()}{c.bitrate ? ` · ${c.bitrate}kbps` : ""} · {c.username}
              </div>
            </div>
            <Button size="sm" variant="outline" onClick={() => onGrab(c)} disabled={running}>
              <DownloadIcon size={13} /> {t.downloads.downloadButton}
            </Button>
          </li>
          );
        })}
      </ul>
      {pages > 1 && (
        <div className="mt-2 flex items-center justify-between text-sm">
          <span className="text-muted">
            {`${start + 1}–${Math.min(start + PAGE_SIZE, results.length)}`} {t.library.paginationOf} {results.length}
          </span>
          <div className="flex gap-2">
            <button disabled={safePage === 0} onClick={() => setPage(safePage - 1)}
              className="inline-flex h-8 items-center gap-1 rounded-none border border-border-strong px-3 hover:bg-elevated disabled:opacity-40"><ChevronLeft size={15} /> {t.library.prevPage}</button>
            <button disabled={start + PAGE_SIZE >= results.length} onClick={() => setPage(safePage + 1)}
              className="inline-flex h-8 items-center gap-1 rounded-none border border-border-strong px-3 hover:bg-elevated disabled:opacity-40">{t.library.nextPage} <ChevronRight size={15} /></button>
          </div>
        </div>
      )}
    </div>
  );
}
