"use client";

import { CircleCheck, HardDrive, Archive } from "lucide-react";
import { SpotifyGlyph } from "./spotify-glyph";
import { SoundcloudGlyph } from "./soundcloud-glyph";
import { TrackPlayButton } from "./track-play-button";
import type { Track } from "@/lib/api";
import { useT } from "@/lib/i18n";

/** Stato di una traccia come icone compatte, condiviso da Libreria e dettaglio
 *  Playlist: pronta per il set, file su disco (blu = posseduta), scartata, e link
 *  Spotify (glifo verde). `context` è la lista ordinata della tabella ospite:
 *  passa al play e abilita prev/next e auto-avanzamento nel player. */
export function TrackStateIcons({ track, context }: { track: Track; context?: Track[] }) {
  const t = useT();
  return (
    <div className="flex items-center gap-2 text-faint">
      <TrackPlayButton track={track} context={context} />
      {track.status === "ready_for_set" && (
        <span title={t.tracks.readyTooltip}>
          <CircleCheck size={14} className="text-fg-strong" />
        </span>
      )}
      {track.has_local_file && (
        <span title={t.tracks.hasFileTooltip}>
          <HardDrive size={14} className="text-[#b8863f]" />
        </span>
      )}
      {track.archived && (
        <span title={t.tracks.archivedTooltip}>
          <Archive size={14} />
        </span>
      )}
      {track.spotify_url && (
        <a
          href={track.spotify_url}
          target="_blank"
          rel="noreferrer"
          title={t.tracks.openOnSpotify}
          className="text-[#1DB954] transition-colors hover:text-[#1ed760]"
        >
          <SpotifyGlyph size={14} />
        </a>
      )}
      {track.platform === "soundcloud" && track.url && (
        <a
          href={track.url}
          target="_blank"
          rel="noreferrer"
          title={t.tracks.openOnSoundcloud}
          className="text-[#ff5500] transition-colors hover:text-[#ff7700]"
        >
          <SoundcloudGlyph size={14} />
        </a>
      )}
    </div>
  );
}
