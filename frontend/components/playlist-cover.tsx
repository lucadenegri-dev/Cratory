import { Music4 } from "lucide-react";
import { API_BASE } from "@/lib/api/base";

// Cover di default per le playlist di sistema (che non hanno artwork_url):
// asset editoriali statici in /public — liked per piattaforma, più Discovery.
const LIKED_COVER: Record<string, string> = {
  spotify: "/cover-liked-spotify.svg",
  soundcloud: "/cover-liked-soundcloud.svg",
};
const DISCOVERY_COVER = "/cover-discovery.svg";
const RATING_TOP_COVER = "/cover-rating-top.svg";

/** Cover di una playlist: artwork reale se presente, altrimenti la cover di
 *  default di sistema (liked per piattaforma, Discovery) e infine il
 *  placeholder con icona. */
export function PlaylistCover({
  artworkUrl,
  platform,
  kind,
  className = "",
  iconSize = 18,
  placeholderClassName = "bg-elevated",
}: {
  artworkUrl?: string | null;
  platform?: string | null;
  kind?: string | null;
  className?: string;
  iconSize?: number;
  placeholderClassName?: string;
}) {
  const fallback =
    kind === "liked" ? LIKED_COVER[platform ?? ""] ?? null
    : kind === "discovery" ? DISCOVERY_COVER
    : kind === "rating_top" ? RATING_TOP_COVER
    : null;
  // La cover caricata dall'utente e' servita dal backend con un URL relativo
  // (`/api/playlists/{id}/artwork`): nel bundle desktop la pagina e il backend
  // sono origini diverse, quindi va premesso API_BASE. Gli URL di piattaforma
  // sono assoluti e restano com'erano.
  const raw = artworkUrl ?? fallback;
  const src = raw && raw.startsWith("/api/") ? API_BASE + raw : raw;
  if (src) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img
        src={src}
        alt=""
        loading="lazy"
        decoding="async"
        className={`${className} rounded-none object-cover`}
      />
    );
  }
  return (
    <span className={`grid place-items-center rounded-none text-faint ${placeholderClassName} ${className}`}>
      <Music4 size={iconSize} />
    </span>
  );
}
