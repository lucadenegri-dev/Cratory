"use client";

import { useEffect, useId, useRef, useState } from "react";

import { TrackCover } from "@/components/track-cover";
import { Input } from "@/components/ui";
import { useT } from "@/lib/i18n";
import type { Track } from "@/lib/api/types";
import { cn } from "@/lib/cn";

const DEBOUNCE_MS = 250;

/* Un campo di testo sulla libreria: i simili partono da una traccia posseduta,
   e qui la si trova per artista o titolo. Il Combobox del DS filtra una lista
   già in mano; qui la lista arriva dal backend a ogni pausa di digitazione, e
   una risposta vecchia non deve sovrascrivere quella nuova (contatore di giro). */
export function DiscoveryTrackSearch({ search, onPick, disabled }: {
  search: (q: string) => Promise<Track[]>;
  onPick: (track: Track) => void;
  disabled?: boolean;
}) {
  const t = useT();
  const [q, setQ] = useState("");
  const [results, setResults] = useState<Track[] | null>(null);
  const [active, setActive] = useState(-1);
  const [open, setOpen] = useState(false);
  const listId = useId();
  const turn = useRef(0);
  const blurTimer = useRef<number | null>(null);
  useEffect(() => () => { if (blurTimer.current != null) window.clearTimeout(blurTimer.current); }, []);

  useEffect(() => {
    const term = q.trim();
    const mine = ++turn.current;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- l'effect risincronizza la lista sulla query (input dell'utente), non su state derivato: campo svuotato = lista via, senza aspettare il debounce
    if (!term) { setResults(null); return; }
    const id = window.setTimeout(() => {
      search(term)
        .then((rows) => { if (turn.current === mine) { setResults(rows); setActive(-1); setOpen(true); } })
        .catch(() => { if (turn.current === mine) setResults([]); });
    }, DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [q, search]);

  const choose = (track: Track) => {
    onPick(track);
    setOpen(false);
    setActive(-1);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!results) return;
    if (e.key === "Escape") { setOpen(false); return; }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      setActive((a) => Math.max(0, Math.min(results.length - 1, e.key === "ArrowDown" ? a + 1 : a - 1)));
      return;
    }
    if (e.key === "Enter" && open && active >= 0 && results[active]) {
      e.preventDefault();
      choose(results[active]);
    }
  };

  return (
    <div className="relative w-full">
      <Input
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={active >= 0 ? `${listId}-opt-${active}` : undefined}
        autoComplete="off"
        value={q}
        disabled={disabled}
        placeholder={t.discovery.trackSearchPlaceholder}
        onFocus={() => setOpen(true)}
        onChange={(e) => setQ(e.target.value)}
        onKeyDown={onKeyDown}
        onBlur={() => { blurTimer.current = window.setTimeout(() => setOpen(false), 120); }}
      />
      <p className="mt-1 text-xs text-muted">{t.discovery.trackSearchHint}</p>
      {open && results !== null && (
        results.length === 0 ? (
          <p className="mt-1 text-xs text-faint">{t.discovery.trackSearchEmpty}</p>
        ) : (
          <ul
            id={listId}
            role="listbox"
            className="absolute left-0 top-10 z-30 mt-1 max-h-72 w-full overflow-y-auto border border-border-strong bg-surface"
          >
            {results.map((track, i) => (
              <li
                key={track.id}
                id={`${listId}-opt-${i}`}
                role="option"
                aria-selected={i === active}
                onMouseDown={(e) => { e.preventDefault(); choose(track); }}
                onMouseEnter={() => setActive(i)}
                className={cn(
                  "flex cursor-pointer items-center gap-3 px-3 py-1.5 text-sm",
                  i === active ? "bg-elevated text-fg" : "text-muted",
                )}
              >
                <TrackCover track={track} className="h-8 w-8 shrink-0" iconSize={12} />
                <span className="truncate">{track.artist} — {track.title}</span>
              </li>
            ))}
          </ul>
        )
      )}
    </div>
  );
}
