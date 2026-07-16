"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

import { discoveryPreview, type DiscoveryPreview } from "@/lib/api";

export type PreviewItem = {
  key: string;
  artist: string;
  title: string;
  discogsId: number | null;
  level: "release" | "track";
  label: string;
};

type Status = "idle" | "loading" | "playing" | "unavailable";

type Ctx = {
  active: PreviewItem | null;
  status: Status;
  data: DiscoveryPreview | null;
  play: (item: PreviewItem) => void;
  stop: () => void;
};

const PreviewCtx = createContext<Ctx | null>(null);

export function PreviewPlayerProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState<PreviewItem | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<DiscoveryPreview | null>(null);
  const reqId = useRef(0);

  const play = useCallback((item: PreviewItem) => {
    const id = ++reqId.current;
    setActive(item);
    setStatus("loading");
    setData(null);
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

  return <PreviewCtx.Provider value={{ active, status, data, play, stop }}>{children}</PreviewCtx.Provider>;
}

export function usePreviewPlayer(): Ctx {
  const ctx = useContext(PreviewCtx);
  if (!ctx) throw new Error("usePreviewPlayer must be used within PreviewPlayerProvider");
  return ctx;
}
