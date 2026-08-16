"use client";

import Link from "next/link";
import { Download as DownloadIcon, Link2, MoreHorizontal, RotateCcw, Search, ShoppingCart } from "lucide-react";
import { Badge, Button, DropdownMenu } from "@/components/ui";
import { TrackCover } from "@/components/track-cover";
import { STORES, storeQuery } from "@/lib/store-links";
import { wishlistStatus, type WishlistStatus } from "@/lib/wishlist-status";
import { trackLabel, type Track } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { withFrom } from "@/lib/back-link";

export type WishlistRowProps = {
  track: Track;
  archived?: boolean;              // vista "mostra archiviate": solo Ripristina + Compra
  downloadsAvailable: boolean;     // slskd configurato e nessun job in corso
  from: string;                    // origine per i link indietro (path+query vivi della pagina, vedi wishlist/page.tsx)
  onDownload: (t: Track) => void;  // auto-pick (mai tentata / riprova)
  onSearch: (t: Track) => void;    // apre SoulseekSearchModal (primaria per review, voce menu per tutti)
  onLinkFile: (t: Track) => void;  // apre LinkLocalFileModal
  onClearOutcome: (t: Track) => void;
  onArchive: (t: Track) => void;   // la conferma sta nella pagina
  onRestore: (t: Track) => void;
  /** Selezione multipla: la checkbox compare solo quando onToggleSelect e' passata
   *  (la vista archiviate non seleziona, vedi app/wishlist/page.tsx). */
  selected?: boolean;
  onToggleSelect?: (t: Track) => void;
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
  track, archived, downloadsAvailable, from,
  onDownload, onSearch, onLinkFile, onClearOutcome, onArchive, onRestore,
  selected, onToggleSelect,
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
  const href = withFrom(`/tracks/${track.id}`, from);

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
          <Button size="sm" onClick={() => onSearch(track)}>
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
      <div className="flex min-w-0 flex-1 items-center gap-2.5">
        {onToggleSelect && (
          <input
            type="checkbox"
            aria-label={t.wishlist.selectRowAria}
            checked={!!selected}
            onChange={() => onToggleSelect(track)}
            className="h-4 w-4 shrink-0 accent-[var(--color-fg)]"
          />
        )}
        {/* Stesso target del titolo: allarga la superficie di click per il mouse,
            ma resta fuori dall'ordine di tab così tastiera e screen reader vedono
            un solo link per traccia. I chip di provenienza sono già <Link>, quindi
            cover e testo non possono stare dentro un unico <a>. */}
        <a href={href} aria-hidden="true" tabIndex={-1} className="shrink-0">
          <TrackCover track={track} className="h-10 w-10" iconSize={16} />
        </a>
        <div className="min-w-0 flex-1">
          <a href={href} className="block truncate hover:text-fg-strong">{trackLabel(track)}</a>
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
              { key: "soulseek", label: t.wishlist.searchSoulseek, onSelect: () => onSearch(track) },
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
