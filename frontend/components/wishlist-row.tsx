"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Download as DownloadIcon, Link2, MoreHorizontal, RotateCcw, Search, ShoppingCart } from "lucide-react";
import { Badge, Button, DropdownMenu } from "@/components/ui";
import { STORES, storeQuery } from "@/lib/store-links";
import { wishlistStatus, type WishlistStatus } from "@/lib/wishlist-status";
import { trackLabel, type Track } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { withFrom } from "@/lib/back-link";

export type WishlistRowProps = {
  track: Track;
  archived?: boolean;              // vista "mostra archiviate": solo Ripristina + Compra
  downloadsAvailable: boolean;     // slskd configurato e nessun job in corso
  onDownload: (t: Track) => void;  // auto-pick (mai tentata / riprova)
  onReview: (t: Track) => void;    // apre DownloadReviewModal
  onLinkFile: (t: Track) => void;  // apre LinkLocalFileModal
  onClearOutcome: (t: Track) => void;
  onArchive: (t: Track) => void;   // la conferma sta nella pagina
  onRestore: (t: Track) => void;
};

const BADGE_TONE: Record<WishlistStatus, "warning" | "danger" | "neutral"> = {
  never: "neutral",
  review: "warning",
  not_found: "neutral",
  failed: "danger",
  downloaded_unlinked: "warning",
};

const MAX_CHIPS = 2;

export function WishlistRow({
  track, archived, downloadsAvailable,
  onDownload, onReview, onLinkFile, onClearOutcome, onArchive, onRestore,
}: WishlistRowProps) {
  const t = useT();
  const status = wishlistStatus(track);
  const BADGE_LABEL: Record<WishlistStatus, string> = {
    never: t.wishlist.badgeNever,
    review: t.wishlist.badgeReview,
    not_found: t.wishlist.badgeNotFound,
    failed: t.wishlist.badgeFailed,
    downloaded_unlinked: t.wishlist.badgeDownloadedUnlinked,
  };
  const detail = status === "failed"
    ? t.downloads.failedReason(track.last_download_reason)
    : track.last_download_reason;
  const chips = track.playlists.slice(0, MAX_CHIPS);
  const extra = track.playlists.length - chips.length;
  const q = storeQuery(track.artist, track.title);
  // Origine per i link indietro di dettaglio traccia e dettaglio playlist.
  const from = usePathname();

  const primary = (() => {
    if (archived) return null;
    switch (status) {
      case "never":
        return (
          <Button size="sm" disabled={!downloadsAvailable} onClick={() => onDownload(track)}>
            <DownloadIcon size={13} /> {t.wishlist.downloadButton}
          </Button>
        );
      case "not_found":
      case "failed":
        return (
          <Button size="sm" disabled={!downloadsAvailable} onClick={() => onDownload(track)}>
            <RotateCcw size={13} /> {t.wishlist.retryButton}
          </Button>
        );
      case "review":
        return (
          <Button size="sm" onClick={() => onReview(track)}>
            <Search size={13} /> {t.wishlist.reviewButton}
          </Button>
        );
      case "downloaded_unlinked":
        return (
          <Button size="sm" onClick={() => onLinkFile(track)}>
            <Link2 size={13} /> {t.wishlist.linkFileButton}
          </Button>
        );
    }
  })();

  return (
    <li className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
      <div className="min-w-0 flex-1">
        <a href={withFrom(`/tracks/${track.id}`, from)} className="block truncate hover:text-fg-strong">{trackLabel(track)}</a>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
          {chips.map((p) => (
            <Link key={p.id} href={withFrom(`/playlists/${p.id}`, from)}
              className="border border-border px-1.5 py-px text-[10px] uppercase tracking-wider text-muted hover:text-fg">
              {p.name}
            </Link>
          ))}
          {extra > 0 && (
            <span className="text-[10px] text-faint" title={track.playlists.slice(MAX_CHIPS).map((p) => p.name).join(", ")}>
              {t.wishlist.provenanceMore(extra)}
            </span>
          )}
          {detail && <span className="text-xs text-muted">{detail}</span>}
        </div>
      </div>
      <span className="flex shrink-0 flex-wrap items-center gap-2">
        <Badge tone={BADGE_TONE[status]}>{BADGE_LABEL[status]}</Badge>
        {archived ? (
          <Button size="sm" variant="outline" onClick={() => onRestore(track)}>
            <RotateCcw size={13} /> {t.wishlist.restoreButton}
          </Button>
        ) : primary}
        <DropdownMenu
          label={<><ShoppingCart size={13} /> {t.wishlist.buyButton}</>}
          items={STORES.map((s) => ({ key: s.key, label: s.label, href: s.url(q) }))}
        />
        {!archived && (
          <DropdownMenu
            label={<MoreHorizontal size={13} />}
            ariaLabel={t.wishlist.moreActionsAria}
            variant="ghost"
            items={[
              { key: "link", label: t.wishlist.linkFileButton, onSelect: () => onLinkFile(track) },
              { key: "clear", label: t.wishlist.clearOutcomeButton, disabled: status === "never", onSelect: () => onClearOutcome(track) },
              { key: "archive", label: t.wishlist.archiveButton, onSelect: () => onArchive(track) },
            ]}
          />
        )}
      </span>
    </li>
  );
}
