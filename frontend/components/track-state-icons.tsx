import { CircleCheck, HardDrive, Archive } from "lucide-react";
import { SpotifyGlyph } from "./spotify-glyph";
import type { Track } from "@/lib/api";

/** Stato di una traccia come icone compatte, condiviso da Libreria e dettaglio
 *  Playlist: pronta per il set, file su disco (blu = posseduta), scartata, e link
 *  Spotify (glifo verde). */
export function TrackStateIcons({ track }: { track: Track }) {
  return (
    <div className="flex items-center gap-2 text-faint">
      {track.status === "ready_for_set" && (
        <span title="Pronta per il set (BPM + tonalità)">
          <CircleCheck size={14} className="text-fg-strong" />
        </span>
      )}
      {track.has_local_file && (
        <span title="File in libreria (su disco)">
          <HardDrive size={14} className="text-[#b8863f]" />
        </span>
      )}
      {track.archived && (
        <span title="Scartata (nell'archivio)">
          <Archive size={14} />
        </span>
      )}
      {track.spotify_url && (
        <a
          href={track.spotify_url}
          target="_blank"
          rel="noreferrer"
          title="Apri su Spotify"
          className="text-[#1DB954] transition-colors hover:text-[#1ed760]"
        >
          <SpotifyGlyph size={14} />
        </a>
      )}
    </div>
  );
}
