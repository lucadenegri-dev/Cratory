"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

import { discoveryPreview, type DiscoveryImportInput, type DiscoveryPreview } from "@/lib/api";

export type PreviewItem = {
  key: string;
  artist: string;
  title: string;
  discogsId: number | null;
  level: "release" | "track";
  label: string;
  /** Payload per l'azione "ADD" (salva il lead in libreria) dal player docked. */
  addInput?: DiscoveryImportInput;
};

export type LocalTrack = {
  id: number;
  title: string;
  artist: string;
  /** Artwork Spotify se presente; il dock ripiega su cover embedded/placeholder. */
  albumArtUrl?: string | null;
};

export type PlaybackSource =
  | { kind: "discovery-preview"; item: PreviewItem }
  | { kind: "local-track"; track: LocalTrack };

type Status = "idle" | "loading" | "playing" | "unavailable";

type Ctx = {
  active: PlaybackSource | null;
  status: Status;
  data: DiscoveryPreview | null;
  play: (source: PlaybackSource) => void;
  stop: () => void;
};

const PlayerCtx = createContext<Ctx | null>(null);

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState<PlaybackSource | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<DiscoveryPreview | null>(null);
  const reqId = useRef(0);

  const play = useCallback((source: PlaybackSource) => {
    const id = ++reqId.current; // invalida qualunque risoluzione preview in volo
    setActive(source);
    setData(null);
    if (source.kind === "local-track") {
      setStatus("playing"); // stream diretto: nessuna risoluzione async
      return;
    }
    // discovery-preview: risoluzione async della sorgente di terzi (iTunes/YouTube)
    setStatus("loading");
    const item = source.item;
    discoveryPreview({ artist: item.artist, title: item.title, discogsId: item.discogsId, level: item.level })
      .then((res) => {
        if (id !== reqId.current) return; // richiesta superata da un nuovo play
        setData(res);
        setStatus(res.kind === "none" ? "unavailable" : "playing");
      })
      .catch(() => {
        if (id !== reqId.current) return;
        setStatus("unavailable");
      });
  }, []);

  const stop = useCallback(() => {
    reqId.current++;
    setActive(null);
    setStatus("idle");
    setData(null);
  }, []);

  return <PlayerCtx.Provider value={{ active, status, data, play, stop }}>{children}</PlayerCtx.Provider>;
}

export function usePlayer(): Ctx {
  const ctx = useContext(PlayerCtx);
  if (!ctx) throw new Error("usePlayer must be used within PlayerProvider");
  return ctx;
}
