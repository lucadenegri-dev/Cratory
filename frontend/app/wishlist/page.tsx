"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Download as DownloadIcon, ExternalLink, Heart, Link2 } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Button, Card, Checkbox, EmptyState, Input, Loading, Select } from "@/components/ui";
import { ButtonLink } from "@/components/button-link";
import { useJobs } from "@/components/jobs-provider";
import { WishlistRow } from "@/components/wishlist-row";
import { SelectionBar } from "@/components/wishlist-selection-bar";
import { SoulseekSearchModal, type SoulseekSearchTarget } from "@/components/soulseek-search-modal";
import { LinkLocalFileModal, type LinkTarget } from "@/components/link-local-file-modal";
import { AutoLinkModal } from "@/components/auto-link-modal";
import { ConfirmModal } from "@/components/confirm-modal";
import {
  apiGet, downloadTrackAuto, enqueueDownloads, errText, ignoreDownload, retryPending,
  slskdStatus, trackLabel, updateTrack, type Track,
} from "@/lib/api";
import { statusTab, wishlistStatus, type WishlistTab } from "@/lib/wishlist-status";
import { useT } from "@/lib/i18n";

type Tab = "all" | WishlistTab;
const TAB_KEYS: Tab[] = ["all", "never", "review", "not_found", "failed"];

// Condivisa fra `rows` (sotto) e la potatura della selezione dentro load():
// stessa nozione di "visibile nella vista corrente" nei due punti, per non
// disallinearle in futuro.
function matchesFilters(tr: Track, tab: Tab, playlistFilter: string, query: string): boolean {
  if (tab !== "all" && statusTab(wishlistStatus(tr)) !== tab) return false;
  if (playlistFilter && !tr.playlists.some((p) => String(p.id) === playlistFilter)) return false;
  const q = query.trim().toLowerCase();
  if (q && !`${tr.artist ?? ""} ${tr.title ?? ""}`.toLowerCase().includes(q)) return false;
  return true;
}

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
  const [info, setInfo] = useState<string | null>(null);

  // Selezione multipla per l'accodamento a lotti (solo vista non archiviata,
  // vedi WishlistRow più sotto). Set<id>, non Set<Track>: le righe vengono
  // ricreate a ogni fetch, l'identità dell'oggetto Track non è stabile.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [enqueuing, setEnqueuing] = useState(false);
  const toggleSelect = useCallback((tr: Track) => {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(tr.id)) next.delete(tr.id); else next.add(tr.id);
      return next;
    });
  }, []);

  // Link alla web UI di slskd (= SLSKD_URL, esposto da /api/slskd/status): per
  // cercare/scaricare a mano quando il download da Cratory non riesce. null se
  // slskd non e' configurato -> il blocco non compare.
  const [slskdWebUrl, setSlskdWebUrl] = useState<string | null>(null);

  const [searchTarget, setSearchTarget] = useState<SoulseekSearchTarget | null>(null);
  const [linking, setLinking] = useState<LinkTarget | null>(null);
  const [autoLink, setAutoLink] = useState(false);
  const [confirmArchive, setConfirmArchive] = useState<Track | null>(null);
  const alive = useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  // Ultimi tab/playlistFilter/query per la potatura della selezione dentro
  // load() (sotto): load() ha come unica dipendenza showArchived per restare
  // client-side sui filtri (nessun refetch a ogni tab/ricerca/playlist), quindi
  // legge i filtri correnti da qui invece che dalle dipendenze della useCallback.
  // Assegnazione di un ref in un effect, non uno setState: nessun problema col
  // lint del React Compiler citato sopra.
  const filtersRef = useRef({ tab, playlistFilter, query });
  useEffect(() => { filtersRef.current = { tab, playlistFilter, query }; }, [tab, playlistFilter, query]);

  const load = useCallback((signal?: AbortSignal) => {
    // limit=0 = tutte (l'endpoint pagina solo se richiesto): filtri e contatori
    // sono client-side, oggi ~55 tracce. `archived=true` restituisce SOLO le
    // archiviate: il toggle sostituisce la vista, non la mescola.
    return apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      has_local_file: "false",
      archived: showArchived ? "true" : undefined,
      sort: "artist", order: "asc", limit: 0,
    }, { signal })
      .then((r) => {
        if (!alive.current) return;
        setItems(r.items);
        setError(null);
        // Le azioni di riga (archivia, azzera esito, download riuscito che rende
        // la traccia "owned", collega file, scelta da ricerca Soulseek) possono
        // far uscire una traccia dalla vista corrente senza che l'utente tocchi
        // un filtro — e tutte ricaricano da qui. Si pota la selezione sulle
        // righe ancora visibili: altrimenti "Accoda" spedirebbe id per tracce
        // che l'utente non vede più selezionate (nel caso dell'archiviazione,
        // un id esplicitamente escluso — il backend non filtra per
        // archived/has_local_file in fase di accodamento).
        setSelected((prev) => {
          if (prev.size === 0) return prev;
          const f = filtersRef.current;
          const visible = new Set(
            r.items.filter((tr) => matchesFilters(tr, f.tab, f.playlistFilter, f.query)).map((tr) => tr.id));
          let changed = false;
          const next = new Set<number>();
          for (const id of prev) {
            if (visible.has(id)) next.add(id); else changed = true;
          }
          return changed ? next : prev;
        });
      })
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

  // Le righe selezionate potrebbero non essere più visibili sotto un filtro
  // diverso: si svuota la selezione (e il messaggio d'accodamento, ormai
  // riferito a un'altra vista) a ogni cambio di tab/ricerca/playlist/archiviate.
  // Fatto nei setter dei filtri (sotto), non in un useEffect: setState sincrono
  // dentro un effect è vietato dal lint del React Compiler di questo repo.
  const clearSelection = useCallback(() => { setSelected(new Set()); setInfo(null); }, []);

  // Stato -> URL (replace + debounce, default fuori dall'URL).
  useEffect(() => {
    if (queryString === searchParams.toString()) return;
    const timer = setTimeout(() => {
      router.replace(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
    }, 300);
    return () => clearTimeout(timer);
  }, [queryString, pathname, router, searchParams]);

  // Da quando la coda (B) è parallela, /status resta "running" per tutta la
  // vita della coda, non più per un singolo download: gatare i bottoni su
  // `running` spegnerebbe TUTTI i download appena se ne accoda uno, il
  // contrario di quello che serve a una coda. Il gate resta solo su
  // `available` — slskd non configurato affatto — l'unico caso dove offrire
  // il download non avrebbe comunque senso.
  const available = jobStatus?.available ?? true;
  const downloadsAvailable = available;

  // Filtro playlist: opzioni derivate dalle tracce (solo playlist rappresentate).
  const playlistOptions = useMemo(() => {
    const seen = new Map<number, string>();
    for (const tr of items ?? []) for (const p of tr.playlists) seen.set(p.id, p.name);
    return [...seen.entries()].sort((a, b) => a[1].localeCompare(b[1]));
  }, [items]);

  const rows = useMemo(
    () => (items ?? []).filter((tr) => matchesFilters(tr, tab, playlistFilter, query)),
    [items, tab, playlistFilter, query],
  );

  const count = useCallback((k: Tab) => (items ?? []).filter(
    (tr) => k === "all" || statusTab(wishlistStatus(tr)) === k).length, [items]);

  const act = async (fn: () => Promise<unknown>, after?: () => void) => {
    setError(null);
    // Come l'errore: un messaggio d'accodamento vecchio non deve sopravvivere
    // alla prossima azione (rilievo review — restava a schermo a oltranza).
    setInfo(null);
    try { await fn(); after?.(); } catch (e) { setError(errText(e)); }
  };
  // Come la barra di selezione multipla, dice com'è andata: la deduplica può
  // saltare la richiesta, e senza un messaggio è indistinguibile da una
  // riuscita — il bottone si preme, non succede nulla di visibile.
  const onDownload = (tr: Track) => act(async () => {
    const res = await downloadTrackAuto(tr.id);
    setInfo(res.enqueued > 0 ? t.wishlist.enqueuedOne : t.wishlist.enqueueAlreadyQueued);
  }, refresh);
  const onClearOutcome = (tr: Track) => act(() => ignoreDownload(tr.id), () => load());
  const onArchive = (tr: Track) => act(() => updateTrack(tr.id, { archived: true }), () => load());
  const onRestore = (tr: Track) => act(() => updateTrack(tr.id, { archived: false }), () => load());
  const retryAll = () => act(() => retryPending(), refresh);

  const onEnqueueSelected = async () => {
    setError(null);
    setInfo(null);
    setEnqueuing(true);
    try {
      const res = await enqueueDownloads([...selected]);
      // `replaced` non può capitare qui (nessun candidato esplicito in un
      // lotto), quindi il messaggio resta a due numeri.
      setInfo(t.wishlist.enqueued(res.enqueued, res.skipped));
      setSelected(new Set());
      refresh();
    } catch (e) {
      setError(errText(e));
    } finally {
      setEnqueuing(false);
    }
  };

  return (
    <PageLayout title={t.wishlist.pageTitle} meta={items?.length || undefined}>
      <div className="space-y-6">
        {!available && <Alert tone="info">{t.downloads.notConfigured}</Alert>}
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {info && <Alert tone="info">{info}</Alert>}

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
                  variant={tab === k ? "primary" : "outline"} onClick={() => { setTab(k); clearSelection(); }}>
                  {TAB_LABEL[k]} ({count(k)})
                </Button>
              ))}
            </div>
            <Input className="h-8 w-56" value={query}
              onChange={(e) => { setQuery(e.target.value); clearSelection(); }}
              placeholder={t.wishlist.searchPlaceholder} />
            <Select className="h-8" value={playlistFilter}
              onChange={(e) => { setPlaylistFilter(e.target.value); clearSelection(); }}>
              <option value="">{t.wishlist.playlistAllOption}</option>
              {playlistOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </Select>
            <Checkbox label={t.wishlist.showArchivedLabel} checked={showArchived}
              onChange={(v) => { setShowArchived(v); setItems(null); clearSelection(); }} />
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
          {!showArchived && (
            <div className="mb-2">
              {/* `canEnqueue`: stesso gate del «Scarica» di riga — senza slskd
                  quelle tracce non partirebbero mai (e il backend risponde 409). */}
              <SelectionBar count={selected.size} busy={enqueuing}
                canEnqueue={downloadsAvailable}
                onEnqueue={onEnqueueSelected} onClear={clearSelection} />
            </div>
          )}
          {rows.length > 0 && (
            <Card>
              <ul className="divide-y divide-border text-sm">
                {rows.map((tr) => (
                  <WishlistRow key={tr.id} track={tr} archived={showArchived}
                    downloadsAvailable={downloadsAvailable} from={from}
                    onDownload={onDownload}
                    onSearch={(x) => setSearchTarget({ track_id: x.id, artist: x.artist, title: x.title })}
                    onLinkFile={(x) => setLinking({ id: x.id, artist: x.artist, title: x.title })}
                    onClearOutcome={onClearOutcome}
                    onArchive={setConfirmArchive}
                    onRestore={onRestore}
                    {...(showArchived ? {} : { selected: selected.has(tr.id), onToggleSelect: toggleSelect })} />
                ))}
              </ul>
            </Card>
          )}
        </section>

        {/* Soulseek: link alla web UI di slskd, ora una riserva. La ricerca
            manuale per traccia vive nel modal aperto da WishlistRow; questo
            blocco resta solo per quando slskd non risponde o serve la sua UI.
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
      </div>

      <SoulseekSearchModal target={searchTarget} onClose={() => setSearchTarget(null)}
        onPicked={() => { setInfo(null); refresh(); setSearchTarget(null); load(); }} />
      <LinkLocalFileModal target={linking} onClose={() => setLinking(null)}
        onLinked={() => { setInfo(null); setLinking(null); load(); }} />
      <AutoLinkModal open={autoLink} onClose={() => setAutoLink(false)} onLinked={() => { setInfo(null); load(); }} />
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
