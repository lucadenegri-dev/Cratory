"use client";

import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ExternalLink, Heart, Link2 } from "lucide-react";
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
  apiGet, downloadQueue, downloadTrackAuto, enqueueDownloads, errText, ignoreDownload,
  slskdStatus, trackLabel, updateTrack, type Track,
} from "@/lib/api";
import { queuedTrackIds, rowTab, type WishlistTab } from "@/lib/wishlist-status";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/cn";

type Tab = "all" | WishlistTab;
// Ordine di ciclo di vita: mai tentata -> in coda -> uno dei tre esiti.
const TAB_KEYS: Tab[] = ["all", "never", "queued", "review", "not_found", "failed"];

// Ordinamento della lista, applicato lato client come i filtri (un solo fetch,
// vedi load()). L'API serve gia' ordinato per artista: quella e' l'identita'.
type SortKey = "artist" | "added_desc" | "added_asc";
const SORT_KEYS: SortKey[] = ["artist", "added_desc", "added_asc"];

// Condivisa fra `rows` (sotto) e la potatura della selezione dentro load():
// stessa nozione di "visibile nella vista corrente" nei due punti, per non
// disallinearle in futuro. `queued` arriva dallo snapshot della coda, non
// dalla traccia: e' un parametro, non un campo.
function matchesFilters(tr: Track, tab: Tab, playlistFilter: string, query: string,
                        queuedIds: ReadonlySet<number>): boolean {
  if (tab !== "all" && rowTab(tr, queuedIds.has(tr.id)) !== tab) return false;
  if (playlistFilter && !tr.playlists.some((p) => String(p.id) === playlistFilter)) return false;
  const q = query.trim().toLowerCase();
  if (q && !`${tr.artist ?? ""} ${tr.title ?? ""}`.toLowerCase().includes(q)) return false;
  return true;
}

// Le tracce senza data finiscono in fondo in entrambi i versi: una data che
// manca non e' "vecchissima" ne' "recentissima", non deve aprire la lista.
function byAdded(a: Track, b: Track, dir: 1 | -1): number {
  if (!a.added_at && !b.added_at) return 0;
  if (!a.added_at) return 1;
  if (!b.added_at) return -1;
  return dir * a.added_at.localeCompare(b.added_at);
}

function WishlistInner() {
  const t = useT();
  const TAB_LABEL: Record<Tab, string> = {
    all: t.wishlist.tabAll,
    never: t.wishlist.tabNever,
    queued: t.wishlist.tabQueued,
    review: t.wishlist.tabReview,
    not_found: t.wishlist.tabNotFound,
    failed: t.wishlist.tabFailed,
  };
  const SORT_LABEL: Record<SortKey, string> = {
    artist: t.wishlist.sortArtist,
    added_desc: t.wishlist.sortAddedDesc,
    added_asc: t.wishlist.sortAddedAsc,
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
  const sortParam = searchParams.get("sort");
  const [sortKey, setSortKey] = useState<SortKey>(
    SORT_KEYS.includes(sortParam as SortKey) ? (sortParam as SortKey) : "artist");

  const [items, setItems] = useState<Track[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  // Selezione multipla per l'accodamento a lotti (solo vista non archiviata,
  // vedi WishlistRow più sotto). Set<id>, non Set<Track>: le righe vengono
  // ricreate a ogni fetch, l'identità dell'oggetto Track non è stabile.
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [enqueuing, setEnqueuing] = useState(false);
  // Tracce in coda (in attesa o in corso), dallo snapshot di /api/downloads/queue:
  // la riga lo mostra al posto dell'ultimo esito. Letto insieme alle tracce in
  // load() e subito dopo ogni accodamento, senza un poller in piu'.
  const [queuedIds, setQueuedIds] = useState<Set<number>>(new Set());
  // load() legge le tracce in coda da un ref e non dalle dipendenze: e' la
  // stessa ragione di filtersRef sopra (restare client-side sui filtri).
  const queuedRef = useRef<ReadonlySet<number>>(queuedIds);
  useEffect(() => { queuedRef.current = queuedIds; }, [queuedIds]);
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
    // La coda si legge a parte e non blocca la lista: se fallisce resta
    // l'ultimo stato noto (peggio un "in coda" vecchio di un giro che una
    // lista che non compare). Una traccia finita in coda esce anche dalla
    // selezione: la checkbox si spegne, il conteggio della barra deve seguire.
    downloadQueue({ signal })
      .then((snap) => {
        if (!alive.current) return;
        const ids = queuedTrackIds(snap.items);
        queuedRef.current = ids;
        setQueuedIds(ids);
        setSelected((prev) => {
          if (prev.size === 0) return prev;
          const next = new Set([...prev].filter((id) => !ids.has(id)));
          return next.size === prev.size ? prev : next;
        });
      })
      .catch(() => undefined);
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
            r.items.filter((tr) => matchesFilters(tr, f.tab, f.playlistFilter, f.query, queuedRef.current))
              .map((tr) => tr.id));
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
    if (sortKey !== "artist") params.set("sort", sortKey);
    return params.toString();
  }, [tab, query, playlistFilter, showArchived, sortKey]);
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

  const rows = useMemo(() => {
    const list = (items ?? []).filter((tr) => matchesFilters(tr, tab, playlistFilter, query, queuedIds));
    if (sortKey === "artist") return list;  // gia' ordinato dall'API
    return [...list].sort((a, b) => byAdded(a, b, sortKey === "added_desc" ? -1 : 1));
  }, [items, tab, playlistFilter, query, queuedIds, sortKey]);

  const count = useCallback((k: Tab) => (items ?? []).filter(
    (tr) => k === "all" || rowTab(tr, queuedIds.has(tr.id)) === k).length, [items, queuedIds]);

  // «Seleziona tutte» in testa lista: prende le righe visibili non in coda.
  // Sostituisce «Riprova tutte» della marginalia, che accodava tutto il
  // pendente a prescindere dai filtri e senza dire quante.
  const selectable = useMemo(() => rows.filter((tr) => !queuedIds.has(tr.id)), [rows, queuedIds]);
  const selectedVisible = useMemo(() => selectable.filter((tr) => selected.has(tr.id)).length, [selectable, selected]);
  const selectAllRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = selectedVisible > 0 && selectedVisible < selectable.length;
    }
  }, [selectedVisible, selectable.length]);
  const toggleSelectAll = (on: boolean) => {
    setInfo(null);
    setSelected(on ? new Set(selectable.map((tr) => tr.id)) : new Set());
  };

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
  // Dopo un accodamento si rilegge subito la coda (load): il poll dei job
  // cambia `processed` solo a fine item, e la riga direbbe "non trovata" per
  // tutto il tempo dell'attesa.
  const onDownload = (tr: Track) => act(async () => {
    const res = await downloadTrackAuto(tr.id);
    setInfo(res.enqueued > 0 ? t.wishlist.enqueuedOne : t.wishlist.enqueueAlreadyQueued);
  }, () => { refresh(); load(); });
  const onClearOutcome = (tr: Track) => act(() => ignoreDownload(tr.id), () => load());
  const onArchive = (tr: Track) => act(() => updateTrack(tr.id, { archived: true }), () => load());
  const onRestore = (tr: Track) => act(() => updateTrack(tr.id, { archived: false }), () => load());

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
      load();
    } catch (e) {
      setError(errText(e));
    } finally {
      setEnqueuing(false);
    }
  };

  // Colonna marginale: filtri e azioni di gruppo escono da sopra la lista e si
  // incolonnano a destra come nelle altre pagine-elenco (library, playlists,
  // labels). La colonna contenuto resta titolo + lista, senza chrome interposto.
  const marginalia = (
    <div className="space-y-5">
      {/* Il blocco degli stati porta la sua etichetta come gli altri campi:
          senza, in cima a una colonna intitolata «Stato», si leggeva come una
          legenda di conteggi invece che come il filtro che e'. */}
      <div>
        <div className="mb-1.5 text-[10px] uppercase tracking-wider text-muted">{t.wishlist.statusTitle}</div>
        <div role="tablist" aria-label={t.wishlist.filterAria} className="-mx-1.5">
        {TAB_KEYS.filter((k) => k === "all" || k === tab || count(k) > 0).map((k) => (
          <button key={k} type="button" role="tab" aria-selected={tab === k}
            onClick={() => { setTab(k); clearSelection(); }}
            className={cn(
              "flex w-full items-baseline gap-2 px-1.5 py-1 text-xs transition-colors",
              tab === k ? "text-fg-strong" : "text-muted hover:text-fg",
            )}>
            <span className={cn("truncate", tab === k && "underline underline-offset-4")}>{TAB_LABEL[k]}</span>
            <span className={cn("tnum ml-auto", tab === k ? "text-fg" : "text-muted")}>{count(k)}</span>
          </button>
        ))}
        </div>
      </div>

      <div className="space-y-2">
        <Input className="h-9" value={query}
          onChange={(e) => { setQuery(e.target.value); clearSelection(); }}
          placeholder={t.wishlist.searchPlaceholder} />
        <Select className="h-9" value={playlistFilter}
          onChange={(e) => { setPlaylistFilter(e.target.value); clearSelection(); }}>
          <option value="">{t.wishlist.playlistAllOption}</option>
          {playlistOptions.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
        </Select>
        {/* L'ordinamento non e' un filtro (non cambia quali righe si vedono),
            quindi non azzera la selezione. */}
        <Select className="h-9" aria-label={t.wishlist.sortAria} value={sortKey}
          onChange={(e) => setSortKey(e.target.value as SortKey)}>
          {SORT_KEYS.map((k) => <option key={k} value={k}>{SORT_LABEL[k]}</option>)}
        </Select>
        <div className="pt-1">
          <Checkbox label={t.wishlist.showArchivedLabel} checked={showArchived}
            onChange={(v) => { setShowArchived(v); setItems(null); clearSelection(); }} />
        </div>
      </div>

      {/* Sotto il filetto restano le due cose che non sono ne' filtro ne' azione
          di riga: il collegamento automatico dei file gia' scaricati e la web UI
          di slskd. «Riprova tutte» e' sparito: e' «seleziona tutte» + «Accoda»
          in testa lista, che in piu' rispetta i filtri e dice quante. */}
      <div className="space-y-2 border-t border-border pt-4">
        <Button size="sm" variant="outline" className="w-full justify-start" onClick={() => setAutoLink(true)}>
          <Link2 size={13} /> {t.downloads.linkAllButton}
        </Button>
        {/* Riserva: la ricerca manuale per traccia vive nel modal aperto dalla
            riga, questo link resta per quando slskd non risponde o serve la sua
            UI. Reso solo se SLSKD_URL e' configurato (web_url != null) — e
            compare anche col demone irraggiungibile, che e' quando serve. */}
        {slskdWebUrl && (
          <ButtonLink href={slskdWebUrl} target="_blank" rel="noopener noreferrer"
            variant="ghost" size="sm" block className="justify-start">
            <ExternalLink size={13} /> {t.wishlist.soulseekOpen}
          </ButtonLink>
        )}
      </div>
    </div>
  );

  return (
    <PageLayout title={t.wishlist.pageTitle}
      meta={items === null ? undefined : rows.length === items.length ? items.length : `${rows.length}/${items.length}`}
      marginaliaTitle={t.wishlist.filtersTitle} marginalia={marginalia}>
      <div className="space-y-4">
        {!available && <Alert tone="info">{t.downloads.notConfigured}</Alert>}
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {info && <Alert tone="info">{info}</Alert>}

        <section>
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
          {!showArchived && selected.size > 0 && (
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
              {!showArchived && (
                <label className="flex cursor-pointer items-center gap-3 border-b border-border px-4 py-1.5">
                  <input type="checkbox" ref={selectAllRef}
                    aria-label={t.wishlist.selectAllAria}
                    checked={selectable.length > 0 && selectedVisible === selectable.length}
                    disabled={selectable.length === 0}
                    onChange={(e) => toggleSelectAll(e.target.checked)}
                    className="h-3.5 w-3.5 accent-[var(--color-fg)] disabled:opacity-40" />
                  <span className="text-[10px] uppercase tracking-wider text-muted">{t.wishlist.selectAllLabel}</span>
                </label>
              )}
              <ul className="divide-y divide-border text-sm">
                {rows.map((tr) => (
                  <WishlistRow key={tr.id} track={tr} archived={showArchived}
                    downloadsAvailable={downloadsAvailable} queued={queuedIds.has(tr.id)} from={from}
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
      </div>

      {/* `notice` e' l'esito che il modal non puo' mostrare da solo (chiudendosi
          si smonta): finisce nello stesso avviso dell'accodamento a lotti. */}
      <SoulseekSearchModal target={searchTarget} onClose={() => setSearchTarget(null)}
        onPicked={(notice) => { setInfo(notice ?? null); refresh(); setSearchTarget(null); load(); }} />
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
