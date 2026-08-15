"use client";

import { createContext, useCallback, useContext, useRef, useState } from "react";

import { discoveryPreview, type DiscoveryImportInput, type DiscoveryPreview } from "@/lib/api";

export type PreviewItem = {
  key: string;
  artist: string;
  title: string;
  /** Id neutro della release. Discogs: "123". Bandcamp: "band_id:item_id". */
  sourceId: string | null;
  source: string;
  level: "release" | "track";
  label: string;
  /** Stream diretto Bandcamp della singola traccia: quando presente, salta la
   *  risoluzione iTunes/YouTube. Cablato nella Task 7 — qui solo il campo. */
  streamUrl?: string | null;
  /** Payload per l'azione "ADD" (salva il lead in libreria) dal player docked. */
  addInput?: DiscoveryImportInput;
};

export type LocalTrack = {
  id: number;
  title: string;
  artist: string;
  /** Artwork Spotify se presente; il dock ripiega su cover embedded/placeholder. */
  albumArtUrl?: string | null;
  /** Voto personale (1-3, o null): mostrato nel dock via RatingDiamond. */
  rating?: number | null;
};

export type PlaybackSource =
  | { kind: "discovery-preview"; item: PreviewItem }
  | { kind: "local-track"; track: LocalTrack };

type Status = "idle" | "loading" | "playing" | "unavailable";

type Ctx = {
  active: PlaybackSource | null;
  status: Status;
  data: DiscoveryPreview | null;
  /** Vero solo quando dall'app esce davvero del suono. `status` dice cosa è
   *  caricato nel dock, non se sta suonando: in pausa resta "playing". Lo
   *  alimenta il dock con gli eventi play/pause/ended dell'elemento audio; la
   *  Home ci attacca l'animazione della consolle. */
  audible: boolean;
  play: (source: PlaybackSource) => void;
  stop: () => void;
  /** Riservato al dock: pubblica lo stato reale dell'elemento audio. */
  setAudible: (v: boolean) => void;
};

const PlayerCtx = createContext<Ctx | null>(null);

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState<PlaybackSource | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<DiscoveryPreview | null>(null);
  const [elementPlaying, setAudible] = useState(false);
  const reqId = useRef(0);

  const play = useCallback((source: PlaybackSource) => {
    const id = ++reqId.current; // invalida qualunque risoluzione preview in volo
    setActive(source);
    setData(null);
    setAudible(false); // la nuova sorgente è muta finché il suo elemento non parte
    if (source.kind === "local-track") {
      setStatus("playing"); // stream diretto: nessuna risoluzione async
      return;
    }
    // discovery-preview: risoluzione async della sorgente di terzi (iTunes/YouTube).
    // Il fallback Discogs (get_release lato backend) vuole un id numerico: su Bandcamp
    // "band_id:item_id" non lo è, quindi niente discogsId fuori da source === "discogs".
    const item = source.item;
    // Bandcamp regala lo stream dentro il risultato del dig: suonarlo subito evita
    // un round-trip e da' il brano intero invece dei 30s di iTunes.
    if (item.streamUrl) {
      setData({
        kind: "itunes", audio_url: item.streamUrl, youtube_video_id: null,
        source_url: null, matched_title: item.title,
      });
      setStatus("playing");
      return;
    }
    setStatus("loading");
    const discogsId = item.source === "discogs" && item.sourceId ? Number(item.sourceId) : null;
    discoveryPreview({ artist: item.artist, title: item.title, discogsId, level: item.level })
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
    setAudible(false);
  }, []);

  /* L'iframe YouTube non espone eventi senza caricare la sua API: quando è
     montato sta suonando in autoplay, quindi lo si conta come audibile. */
  const audible = elementPlaying || (status === "playing" && data?.kind === "youtube");

  return (
    <PlayerCtx.Provider value={{ active, status, data, audible, play, stop, setAudible }}>
      {children}
    </PlayerCtx.Provider>
  );
}

export function usePlayer(): Ctx {
  const ctx = useContext(PlayerCtx);
  if (!ctx) throw new Error("usePlayer must be used within PlayerProvider");
  return ctx;
}
