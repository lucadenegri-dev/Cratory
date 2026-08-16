"use client";

import Link from "next/link";
import { Download as DownloadIcon, Link2, MoreHorizontal, RotateCcw, Search } from "lucide-react";
import { Button, DropdownMenu, type MenuItem } from "@/components/ui";
import { TrackCover } from "@/components/track-cover";
import { STORES, storeQuery } from "@/lib/store-links";
import { wishlistStatus, type WishlistStatus } from "@/lib/wishlist-status";
import { trackLabel, type Track } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { withFrom } from "@/lib/back-link";

export type WishlistRowProps = {
  track: Track;
  archived?: boolean;              // vista "mostra archiviate": solo Ripristina + Compra
  downloadsAvailable: boolean;     // slskd configurato (vedi app/wishlist/page.tsx)
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

/* Lo stato e' una colonna tipografica, non un badge: 30 rettangoli pieni in
   colonna erano la fonte di rumore principale della lista, e il design system
   (docs/DESIGN.md) fa gerarchia con peso/case/tracking, non con riempimenti.
   `fg-strong` = tocca all'utente, `muted` = esito di routine, `danger` = fallita
   (l'unico rosso del sistema, qui e' davvero un errore). */
const STATUS_TONE: Record<WishlistStatus, string> = {
  never: "text-muted",
  not_found: "text-muted",
  review: "text-fg-strong",
  failed: "text-danger",
  downloaded_unlinked: "text-fg-strong",
};

const MAX_CHIPS = 2;

export function WishlistRow({
  track, archived, downloadsAvailable, from,
  onDownload, onSearch, onLinkFile, onClearOutcome, onArchive, onRestore,
  selected, onToggleSelect,
}: WishlistRowProps) {
  const t = useT();
  const status = wishlistStatus(track);
  const STATUS_LABEL: Record<WishlistStatus, string> = {
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
    if (archived) {
      return (
        <Button size="sm" variant="outline" className="w-full" onClick={() => onRestore(track)}>
          <RotateCcw size={13} /> {t.wishlist.restoreButton}
        </Button>
      );
    }
    switch (status) {
      case "never":
        return (
          <Button size="sm" className="w-full" disabled={!downloadsAvailable} onClick={() => onDownload(track)}>
            <DownloadIcon size={13} /> {t.wishlist.downloadButton}
          </Button>
        );
      case "not_found":
      case "failed":
        return (
          <Button size="sm" className="w-full" disabled={!downloadsAvailable} onClick={() => onDownload(track)}>
            <RotateCcw size={13} /> {t.wishlist.retryButton}
          </Button>
        );
      case "review":
        return (
          <Button size="sm" className="w-full" onClick={() => onSearch(track)}>
            <Search size={13} /> {t.wishlist.reviewButton}
          </Button>
        );
      case "downloaded_unlinked":
        return (
          <Button size="sm" className="w-full" onClick={() => onLinkFile(track)}>
            <Link2 size={13} /> {t.wishlist.linkFileButton}
          </Button>
        );
    }
  })();

  // Un solo menu per riga. «Compra» era un secondo dropdown a piena evidenza su
  // ogni riga — una via di fuga renderizzata 30 volte con lo stesso peso
  // dell'azione vera: ora e' una sezione di questo, sotto un filetto.
  const menuItems: MenuItem[] = [
    ...(archived ? [] : [
      { key: "soulseek", label: t.wishlist.searchSoulseek, onSelect: () => onSearch(track) },
      { key: "link", label: t.wishlist.linkFileButton, onSelect: () => onLinkFile(track) },
      { key: "clear", label: t.wishlist.clearOutcomeButton, disabled: status === "never", onSelect: () => onClearOutcome(track) },
      { key: "archive", label: t.wishlist.archiveButton, onSelect: () => onArchive(track) },
    ]),
    { key: "buy", label: t.wishlist.buyButton, section: true },
    ...STORES.map((s) => ({ key: s.key, label: s.label, href: s.url(q) })),
  ];

  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 py-2">
      {/* `min-w-60`: sotto i 240px il titolo non si stringe oltre, e' la zona
          azioni ad andare a capo come blocco. Senza, la riga non andava mai a
          capo e a 600px il titolo si riduceva a una decina di caratteri. */}
      <div className="flex min-w-60 flex-1 items-center gap-3">
        {onToggleSelect && (
          <input
            type="checkbox"
            aria-label={t.wishlist.selectRowAria}
            checked={!!selected}
            onChange={() => onToggleSelect(track)}
            className="h-3.5 w-3.5 shrink-0 accent-[var(--color-fg)]"
          />
        )}
        {/* Stesso target del titolo: allarga la superficie di click per il mouse,
            ma resta fuori dall'ordine di tab così tastiera e screen reader vedono
            un solo link per traccia. I chip di provenienza sono già <Link>, quindi
            cover e testo non possono stare dentro un unico <a>. */}
        <a href={href} aria-hidden="true" tabIndex={-1} className="shrink-0">
          <TrackCover track={track} className="h-8 w-8" iconSize={14} />
        </a>
        <div className="min-w-0 flex-1">
          <a href={href} className="block truncate text-fg hover:text-fg-strong">{trackLabel(track)}</a>
          {/* Provenienza e motivo dell'esito sullo stesso rigo ma distinti dal
              case: le playlist restano label uppercase (grammatica del sistema),
              il motivo e' prosa. Separatore `faint` fra i due mondi. */}
          {(chips.length > 0 || detail) && (
            <div className="mt-0.5 flex flex-wrap items-baseline gap-x-1.5 text-[11px] leading-tight">
              {chips.map((p, i) => (
                <span key={p.id} className="flex items-baseline gap-x-1.5">
                  {i > 0 && <span className="text-faint">·</span>}
                  <Link href={withFrom(`/playlists/${p.id}`, from)}
                    className="text-[10px] uppercase tracking-wider text-muted underline-offset-2 hover:text-fg-strong hover:underline">
                    {p.name}
                  </Link>
                </span>
              ))}
              {extra > 0 && (
                <span className="text-[10px] text-muted" title={track.playlists.slice(MAX_CHIPS).map((p) => p.name).join(", ")}>
                  {t.wishlist.provenanceMore(extra)}
                </span>
              )}
              {/* Separatore dentro lo span del motivo, non accanto: se il motivo
                  va a capo il `·` scende con lui invece di restare appeso in
                  fondo alla riga della provenienza. */}
              {detail && (
                <span className="text-muted">
                  {chips.length > 0 && <span className="text-faint">· </span>}
                  {detail}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
      {/* Zona azioni a larghezze fisse: stato e bottone si incolonnano lungo
          tutta la lista invece di franare a destra riga per riga. Sotto il
          breakpoint va a capo come blocco unico, non a pezzi. */}
      <div className="ml-auto flex shrink-0 items-center gap-3">
        <span className={`w-28 text-[10px] uppercase leading-tight tracking-wider ${STATUS_TONE[status]}`}>
          {STATUS_LABEL[status]}
        </span>
        <span className="w-36">{primary}</span>
        <DropdownMenu
          label={<MoreHorizontal size={13} />}
          ariaLabel={t.wishlist.moreActionsAria}
          variant="ghost"
          items={menuItems}
        />
      </div>
    </li>
  );
}
