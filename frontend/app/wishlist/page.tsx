"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Download as DownloadIcon, ExternalLink, Heart, Link2 } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Button, Card, Checkbox, EmptyState, Input, Loading, Select } from "@/components/ui";
import { ButtonLink } from "@/components/button-link";
import { useJobs } from "@/components/jobs-provider";
import { WishlistRow } from "@/components/wishlist-row";
import { DownloadReviewModal, type ReviewTarget } from "@/components/download-review-modal";
import { LinkLocalFileModal, type LinkTarget } from "@/components/link-local-file-modal";
import { AutoLinkModal } from "@/components/auto-link-modal";
import { ConfirmModal } from "@/components/confirm-modal";
import {
  apiGet, downloadTrackAuto, errText, ignoreDownload, retryPending,
  slskdStatus, trackLabel, updateTrack, type Track,
} from "@/lib/api";
import { statusTab, wishlistStatus, type WishlistTab } from "@/lib/wishlist-status";
import { useT } from "@/lib/i18n";

type Tab = "all" | WishlistTab;
const TAB_KEYS: Tab[] = ["all", "never", "review", "not_found", "failed"];

function WishlistInner() {
  const t = useT();
  const TAB_LABEL: Record<Tab, string> = {
    all: t.wishlist.tabAll,
    never: t.wishlist.tabNever,
    review: t.wishlist.tabReview,
    not_found: t.wishlist.tabNotFound,
    failed: t.wishlist.tabFailed,
  };
  const { download: jobStatus, refresh } = useJobs();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  // Filtri persistiti nella query string (pattern library/downloads): stato
  // iniziale dall'URL, modifiche riflesse con router.replace + debounce.
  const tabParam = searchParams.get("tab");
  const [tab, setTab] = useState<Tab>(TAB_KEYS.includes(tabParam as Tab) ? (tabParam as Tab) : "all");
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [playlistFilter, setPlaylistFilter] = useState(searchParams.get("playlist") ?? "");
  const [showArchived, setShowArchived] = useState(searchParams.get("archived") === "1");

  const [items, setItems] = useState<Track[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Link alla web UI di slskd (= SLSKD_URL, esposto da /api/slskd/status): per
  // cercare/scaricare a mano quando il download da Cratory non riesce. null se
  // slskd non e' configurato -> il blocco non compare.
  const [slskdWebUrl, setSlskdWebUrl] = useState<string | null>(null);

  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [linking, setLinking] = useState<LinkTarget | null>(null);
  const [autoLink, setAutoLink] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState<Track | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const load = useCallback((signal?: AbortSignal) => {
    // limit=0 = tutte (l'endpoint pagina solo se richiesto): filtri e contatori
    // sono client-side, oggi ~55 tracce. `archived=true` restituisce SOLO le
    // archiviate: il toggle sostituisce la vista, non la mescola.
    return apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      has_local_file: "false",
      archived: showArchived ? "true" : undefined,
      sort: "artist", order: "asc", limit: 0,
    }, { signal })
      .then((r) => { if (alive.current) { setItems(r.items); setError(null); } })
      .catch((e) => { if (e?.name !== "AbortError" && alive.current) setError(errText(e)); });
  }, [showArchived]);

  // Ricarica quando il job produce esiti (processed cambia durante il run).
  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    return () => ac.abort();
  }, [load, jobStatus?.status, jobStatus?.processed]);

  // Solo per il link "Apri slskd": web_url resta valorizzato anche se il demone
  // e' irraggiungibile (e' proprio quando serve andare a cercare a mano).
  useEffect(() => {
    slskdStatus().then((s) => alive.current && setSlskdWebUrl(s.web_url)).catch(() => undefined);
  }, []);

  // Querystring corrente derivata dallo stato dei filtri: unica fonte sia per la
  // sincronizzazione dell'URL (sotto) sia per il `from` che WishlistRow porta
  // verso dettaglio traccia e dettaglio playlist, cosi' il back-link torna
  // esattamente su questa vista filtrata (stesso pattern di library/page.tsx:
  // si usa lo stato vivo, NON searchParams, che e' indietro di un debounce
  // rispetto ai filtri appena toccati).
  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (tab !== "all") params.set("tab", tab);
    if (query) params.set("q", query);
    if (playlistFilter) params.set("playlist", playlistFilter);
    if (showArchived) params.set("archived", "1");
    return params.toString();
  }, [tab, query, playlistFilter, showArchived]);
  const from = queryString ? `${pathname}?${queryString}` : pathname;

  // Stato -> URL (replace + debounce, default fuori dall'URL).
  useEffect(() => {
    if (queryString === searchParams.toString()) return;
    const timer = setTimeout(() => {
      router.replace(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
    }, 300);
    return () => clearTimeout(timer);
  }, [queryString, pathname, router, searchParams]);

  const available = jobStatus?.available ?? true;
  const running = jobStatus?.status === "running";
  const downloadsAvailable = available && !running;

  // Filtro playlist: opzioni derivate dalle tracce (solo playlist rappresentate).
  const playlistOptions = useMemo(() => {
    const seen = new Map<number, string>();
    for (const tr of items ?? []) for (const p of tr.playlists) seen.set(p.id, p.name);
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [items]);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (items ?? []).filter((tr) => {
      if (tab !== "all" && statusTab(wishlistStatus(tr)) !== tab) return false;
      if (playlistFilter && !tr.playlists.some((p) => String(p.id) === playlistFilter)) return false;
      if (q && !`${tr.artist ?? ""} ${tr.title ?? ""}`.toLowerCase().includes(q)) return false;
      return true;
    });
  }, [items, tab, playlistFilter, query]);

  const count = useCallback((k: Tab) => (items ?? []).filter(
    (tr) => k === "all" || statusTab(wishlistStatus(tr)) === k).length, [items]);

  const act = async (fn: () => Promise<unknown>, after?: () => void) => {
    setError(null);
    try { await fn(); after?.(); } catch (e) { setError(errText(e)); }
  };
  const onDownload = (tr: Track) => act(() => downloadTrackAuto(tr.id), refresh);
  const onClearOutcome = (tr: Track) => act(() => ignoreDownload(tr.id), () => load());
  const onArchive = (tr: Track) => act(() => updateTrack(tr.id, { archived: true }), () => load());
  const onRestore = (tr: Track) => act(() => updateTrack(tr.id, { archived: false }), () => load());
  const retryAll = () => act(() => retryPending(), refresh);

  return (
    <PageLayout title={t.wishlist.pageTitle} meta={items?.length || undefined}>
      <div className="space-y-6">
        {!available && <Alert tone="info">{t.downloads.notConfigured}</Alert>}
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        {/* Soulseek: link alla web UI di slskd per cercare/scaricare a mano.
            Reso solo se SLSKD_URL e' configurato (web_url != null); compare anche
            quando il demone e' irraggiungibile — che e' proprio quando serve. */}
        {slskdWebUrl && (
          <section>
            <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.wishlist.soulseekHeading}</div>
            <ButtonLink href={slskdWebUrl} target="_blank" rel="noopener noreferrer" variant="outline" size="sm">
              <ExternalLink size={14} /> {t.wishlist.soulseekOpen}
            </ButtonLink>
            <p className="mt-2 text-sm text-faint">{t.wishlist.soulseekHint}</p>
          </section>
        )}

        {/* Azioni di gruppo */}
        <section>
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.wishlist.bulkHeading}</div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" onClick={retryAll} disabled={!downloadsAvailable}>
              <DownloadIcon size={13} /> {t.downloads.retryAllButton}
            </Button>
            <Button variant="outline" onClick={() => setAutoLink(true)}>
              <Link2 size={13} /> {t.downloads.linkAllButton}
            </Button>
          </div>
        </section>

        {/* Filtri */}
        <section>
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <div className="flex flex-wrap gap-1.5" role="tablist" aria-label={t.wishlist.filterAria}>
              {TAB_KEYS.map((k) => (
                <Button key={k} size="sm" role="tab" aria-selected={tab === k}
                  variant={tab === k ? "primary" : "outline"} onClick={() => setTab(k)}>
                  {TAB_LABEL[k]} ({count(k)})
                </Button>
              ))}
            </div>
            <Input className="h-8 w-56" value={query} onChange={(e) => setQuery(e.target.value)}
              placeholder={t.wishlist.searchPlaceholder} />
            <Select className="h-8" value={playlistFilter} onChange={(e) => setPlaylistFilter(e.target.value)}>
              <option value="">{t.wishlist.playlistAllOption}</option>
              {playlistOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </Select>
            <Checkbox label={t.wishlist.showArchivedLabel} checked={showArchived}
              onChange={(v) => { setShowArchived(v); setItems(null); }} />
          </div>

          {items === null && <Loading />}
          {items !== null && rows.length === 0 && (() => {
            // Tre casi distinti (title e body condividono la stessa logica): lista
            // davvero vuota (per vista) vs. tracce presenti ma escluse dal filtro
            // corrente (tab/testo/playlist) — "nessuna archiviata" non deve comparire
            // se archiviate esistono ma il filtro non ne mostra nessuna.
            const emptyKind = showArchived && items.length === 0 ? "archived"
              : items.length === 0 ? "none"
              : "filtered";
            const TITLE = {
              archived: t.wishlist.archivedEmptyTitle,
              none: t.wishlist.emptyTitle,
              filtered: t.wishlist.emptyFilteredTitle,
            } as const;
            const BODY = {
              archived: t.wishlist.archivedEmptyBody,
              none: t.wishlist.emptyBody,
              filtered: t.wishlist.emptyFilteredBody,
            } as const;
            return (
              <EmptyState icon={<Heart size={28} />} title={TITLE[emptyKind]}>
                {BODY[emptyKind]}
              </EmptyState>
            );
          })()}
          {rows.length > 0 && (
            <Card>
              <ul className="divide-y divide-border text-sm">
                {rows.map((tr) => (
                  <WishlistRow key={tr.id} track={tr} archived={showArchived}
                    downloadsAvailable={downloadsAvailable} from={from}
                    onDownload={onDownload}
                    onReview={(x) => setReview({ track_id: x.id, artist: x.artist, title: x.title })}
                    onLinkFile={(x) => setLinking({ id: x.id, artist: x.artist, title: x.title })}
                    onClearOutcome={onClearOutcome}
                    onArchive={setConfirmArchive}
                    onRestore={onRestore} />
                ))}
              </ul>
            </Card>
          )}
        </section>
      </div>

      <DownloadReviewModal target={review} onClose={() => setReview(null)}
        onPicked={() => { refresh(); setReview(null); load(); }} />
      <LinkLocalFileModal target={linking} onClose={() => setLinking(null)}
        onLinked={() => { setLinking(null); load(); }} />
      <AutoLinkModal open={autoLink} onClose={() => setAutoLink(false)} onLinked={() => load()} />
      <ConfirmModal open={confirmArchive !== null}
        message={confirmArchive ? t.wishlist.archiveConfirm(trackLabel(confirmArchive)) : ""}
        onConfirm={() => { const tr = confirmArchive; setConfirmArchive(null); if (tr) onArchive(tr); }}
        onClose={() => setConfirmArchive(null)} />
    </PageLayout>
  );
}

// useSearchParams richiede un boundary Suspense sulle pagine statiche (Next 16),
// stesso pattern di library/downloads/set-builder.
export default function WishlistPage() {
  return <Suspense><WishlistInner /></Suspense>;
}
