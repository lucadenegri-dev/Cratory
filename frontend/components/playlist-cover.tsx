import { Music4 } from "lucide-react";

// Cover di default per le playlist "liked" (che non hanno artwork_url dal fetch):
// asset editoriali statici in /public, uno per piattaforma.
const LIKED_COVER: Record<string, string> = {
  spotify: "/cover-liked-spotify.svg",
  soundcloud: "/cover-liked-soundcloud.svg",
};

/** Cover di una playlist: artwork reale se presente, altrimenti la cover di
 *  default dei liked (per piattaforma) e infine il placeholder con icona. */
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
  const fallback = kind === "liked" ? LIKED_COVER[platform ?? ""] ?? null : null;
  const src = artworkUrl ?? fallback;
  if (src) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={src} alt="" className={`${className} rounded-none object-cover`} />;
  }
  return (
    <span className={`grid place-items-center rounded-none text-faint ${placeholderClassName} ${className}`}>
      <Music4 size={iconSize} />
    </span>
  );
}
