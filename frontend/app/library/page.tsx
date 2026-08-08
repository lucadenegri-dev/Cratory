"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Pencil, List, LayoutGrid } from "lucide-react";
import { apiGet, errText, fmtDate, fmtDuration, type Track } from "@/lib/api";
import { Input, Select, Checkbox, Alert, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { TrackEditModal } from "@/components/track-edit-modal";
import { TrackCover } from "@/components/track-cover";
import { TrackStateIcons } from "@/components/track-state-icons";
import { KeyBadge } from "@/components/key-badge";
import { RatingDiamond } from "@/components/rating-diamond";
import { LibraryTrackGrid } from "@/components/library-track-grid";
import { useT } from "@/lib/i18n";

type Order = "asc" | "desc";

function LibraryInner() {
  const t = useT();
  const STATUS_OPTIONS: [string, string][] = [
    ["ready_for_set", t.library.statusReadyOption],
    ["imported", t.library.statusImportedOption],
  ];
  const [items, setItems] = useState<Track[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const PAGE_SIZE = 50;

  // Filtri/sort/paginazione persistiti nella query string: lo stato iniziale viene
  // dall'URL (così tornando da un dettaglio non si perde nulla) e ogni modifica viene
  // riflessa nell'URL con router.replace (vedi effect più sotto). I default restano
  // fuori dall'URL per tenerlo pulito. useSearchParams() è coerente fra SSR e client
  // (niente hydration mismatch) e resta reattivo se il param cambia da fuori.
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [offset, setOffset] = useState(() => Math.max(0, Number(searchParams.get("offset")) || 0));
  const [artist, setArtist] = useState(searchParams.get("artist") ?? "");
  const [title, setTitle] = useState(searchParams.get("title") ?? "");
  // Filtro genere pre-impostato via query param (es. link "Generi" dalla dashboard):
  // se il param cambia mentre si è già sulla pagina, il filtro si aggiorna e la
  // paginazione riparte. Il ref evita di azzerare l'offset al mount (o quando è il
  // nostro stesso replace a riscrivere l'URL con lo stesso valore).
  const genreParam = searchParams.get("genre") ?? "";
  const [genre, setGenre] = useState(genreParam);
  const genreParamSeen = useRef(genreParam);
  useEffect(() => {
    if (genreParam === genreParamSeen.current) return;
    genreParamSeen.current = genreParam;
    setGenre(genreParam);
    setOffset(0);
  }, [genreParam]);
  const [source, setSource] = useState(searchParams.get("source") ?? "");
  const [status, setStatus] = useState(searchParams.get("status") ?? "");
  const [bpmMin, setBpmMin] = useState(searchParams.get("bpm_min") ?? "");
  const [bpmMax, setBpmMax] = useState(searchParams.get("bpm_max") ?? "");
  const [key, setKey] = useState(searchParams.get("key") ?? "");
  const [incomplete, setIncomplete] = useState(searchParams.get("incomplete") === "1");
  const [owned, setOwned] = useState(searchParams.get("owned") ?? ""); // "" = tutte | "true" = possedute | "false" = wishlist
  const [rating, setRating] = useState(searchParams.get("rating") ?? "");
  const [sort, setSort] = useState(searchParams.get("sort") ?? "");
  const [order, setOrder] = useState<Order>(searchParams.get("order") === "desc" ? "desc" : "asc");
  const [editing, setEditing] = useState<Track | null>(null);
  const [view, setView] = useState<"list" | "grid">("list");
  // Griglia: nessuna paginazione, si caricano tutte le tracce (limit=0 = "tutte" lato API).
  const limit = view === "grid" ? 0 : PAGE_SIZE;
  // Cambio vista: riparti da capo (in griglia l'offset non è usato). Il ref salta il
  // primo run al mount per non azzerare l'offset appena ripristinato dall'URL.
  const viewMounted = useRef(false);
  useEffect(() => {
    if (!viewMounted.current) { viewMounted.current = true; return; }
    setOffset(0);
  }, [view]);

  // Querystring corrente derivata dallo stato dei filtri/sort/paginazione: unica
  // fonte sia per la sincronizzazione dell'URL (sotto) sia per il param `from` che
  // i link verso il dettaglio traccia portano con sé, cosi il back-link dal
  // dettaglio puo' ricostruire la stessa vista filtrata (vedi tracks/[id]/page.tsx).
  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    if (artist) params.set("artist", artist);
    if (title) params.set("title", title);
    if (genre) params.set("genre", genre);
    if (source) params.set("source", source);
    if (status) params.set("status", status);
    if (owned) params.set("owned", owned);
    if (bpmMin) params.set("bpm_min", bpmMin);
    if (bpmMax) params.set("bpm_max", bpmMax);
    if (key) params.set("key", key);
    if (incomplete) params.set("incomplete", "1");
    if (rating) params.set("rating", rating);
    if (sort) {
      params.set("sort", sort);
      if (order !== "asc") params.set("order", order);
    }
    if (offset > 0) params.set("offset", String(offset));
    return params.toString();
  }, [artist, title, genre, source, status, owned, bpmMin, bpmMax, key, incomplete, rating, sort, order, offset]);
  // Suffisso `?from=` per i link verso il dettaglio traccia: porta con sé path +
  // filtri/sort/paginazione, così il link indietro là torna esattamente qui.
  // NB: si usa `queryString` (lo stato vivo) e non searchParams, che è indietro
  // di un debounce rispetto ai filtri appena toccati.
  const trackLinkQuery = `?from=${encodeURIComponent(queryString ? `${pathname}?${queryString}` : pathname)}`;

  // Stato -> URL: replace (non push, niente cronologia inquinata) con un debounce
  // leggero per non riscrivere l'URL a ogni tasto negli input di testo.
  useEffect(() => {
    if (queryString === searchParams.toString()) return;
    const timer = setTimeout(() => {
      router.replace(queryString ? `${pathname}?${queryString}` : pathname, { scroll: false });
    }, 300);
    return () => clearTimeout(timer);
  }, [queryString, pathname, router, searchParams]);
  // Persistenza: letta solo lato client (mai in render/SSR) per non rompere l'hydration.
  useEffect(() => {
    const saved = localStorage.getItem("cratory:library:view");
    if (saved === "grid" || saved === "list") setView(saved);
  }, []);
  useEffect(() => {
    localStorage.setItem("cratory:library:view", view);
  }, [view]);

  const load = useCallback((signal?: AbortSignal) => {
    return apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      artist, title, genre, source, status, bpm_min: bpmMin, bpm_max: bpmMax, key,
      incomplete_metadata: incomplete ? true : undefined,
      has_local_file: owned || undefined,
      rating: rating ? Number(rating) : undefined,
      sort: sort || undefined, order: sort ? order : undefined,
      limit, offset,
    }, { signal })
      .then((r) => { setItems(r.items); setTotal(r.total); setError(null); });
  }, [artist, title, genre, source, status, bpmMin, bpmMax, key, incomplete, owned, rating, sort, order, offset, view]);

  useEffect(() => {
    const ac = new AbortController();
    const timer = setTimeout(() => {
      load(ac.signal).catch((e) => { if (e?.name !== "AbortError") setError(errText(e)); });
    }, 250);
    return () => { clearTimeout(timer); ac.abort(); };
  }, [load]);

  const cell = "px-2 py-2";

  const toggleSort = (col: string) => {
    if (sort === col) setOrder(order === "asc" ? "desc" : "asc");
    else { setSort(col); setOrder("asc"); }
    setOffset(0);
  };

  const th = (label: string, col: string, numeric = false) => {
    const active = sort === col;
    return (
      <th
        aria-sort={active ? (order === "asc" ? "ascending" : "descending") : undefined}
        className={`${numeric ? "tnum " : ""}whitespace-nowrap ${active ? "text-fg" : ""}`}
      >
        <button
          type="button"
          onClick={() => toggleSort(col)}
          title={t.library.sortColumnHint}
          className={`${cell} flex w-full cursor-pointer select-none items-center gap-1 text-left uppercase tracking-wide transition-colors hover:text-fg`}
        >
          {label}
          {active && (order === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
        </button>
      </th>
    );
  };

  const hasActiveFilters = Boolean(
    artist || title || genre || source || status || bpmMin || bpmMax || key || incomplete || owned || rating
  );

  const filters = (
    <div className="space-y-2">
      <Input className="h-9" placeholder={t.library.filterArtistPlaceholder} value={artist} onChange={(e) => { setArtist(e.target.value); setOffset(0); }} />
      <Input className="h-9" placeholder={t.library.filterTitlePlaceholder} value={title} onChange={(e) => { setTitle(e.target.value); setOffset(0); }} />
      <Input className="h-9" placeholder={t.library.filterGenrePlaceholder} value={genre} onChange={(e) => { setGenre(e.target.value); setOffset(0); }} />
      <Select className="h-9" value={source} onChange={(e) => { setSource(e.target.value); setOffset(0); }}>
        <option value="">{t.library.sourceAllOption}</option>
        <option value="spotify">{t.library.sourceSpotifyOption}</option>
        <option value="soundcloud">{t.library.sourceSoundcloudOption}</option>
        <option value="manual">{t.library.sourceManualOption}</option>
        <option value="local_files">{t.library.sourceLocalFilesOption}</option>
      </Select>
      <Select className="h-9" value={status} onChange={(e) => { setStatus(e.target.value); setOffset(0); }}>
        <option value="">{t.library.statusAllOption}</option>
        {STATUS_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </Select>
      <Select className="h-9" value={owned} onChange={(e) => { setOwned(e.target.value); setOffset(0); }}>
        <option value="">{t.library.ownedAllOption}</option>
        <option value="true">{t.library.ownedTrueOption}</option>
        <option value="false">{t.library.ownedFalseOption}</option>
      </Select>
      <Select className="h-9" value={rating} onChange={(e) => { setRating(e.target.value); setOffset(0); }}>
        <option value="">{t.tracks.ratingLabel}</option>
        <option value="1">1</option>
        <option value="2">2</option>
        <option value="3">3</option>
      </Select>
      <div className="grid grid-cols-2 gap-2">
        <Input className="h-9" type="number" placeholder={t.library.bpmMinPlaceholder} value={bpmMin} onChange={(e) => { setBpmMin(e.target.value); setOffset(0); }} />
        <Input className="h-9" type="number" placeholder={t.library.bpmMaxPlaceholder} value={bpmMax} onChange={(e) => { setBpmMax(e.target.value); setOffset(0); }} />
      </div>
      <Input className="h-9" placeholder={t.library.keyPlaceholder} value={key} onChange={(e) => { setKey(e.target.value); setOffset(0); }} />
      <div className="pt-1"><Checkbox label={t.library.incompleteOnlyLabel} checked={incomplete} onChange={(v) => { setIncomplete(v); setOffset(0); }} /></div>
    </div>
  );

  const viewToggle = (
    <div className="inline-flex rounded-none border border-border bg-surface p-0.5">
      <button
        type="button"
        onClick={() => setView("list")}
        aria-pressed={view === "list"}
        title={t.library.viewListLabel}
        className={`rounded-none px-2.5 py-1 transition-colors ${view === "list" ? "bg-elevated text-fg" : "text-muted hover:text-fg"}`}
      >
        <List size={15} />
      </button>
      <button
        type="button"
        onClick={() => setView("grid")}
        aria-pressed={view === "grid"}
        title={t.library.viewGridLabel}
        className={`rounded-none px-2.5 py-1 transition-colors ${view === "grid" ? "bg-elevated text-fg" : "text-muted hover:text-fg"}`}
      >
        <LayoutGrid size={15} />
      </button>
    </div>
  );

  return (
    <PageLayout title={t.library.title} meta={t.library.tracksMeta(total)} action={viewToggle} marginaliaTitle={t.library.filtersTitle} marginalia={filters}>
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {items === null && <Loading />}
      {items?.length === 0 && (hasActiveFilters ? (
        <div className="py-10 text-center text-sm text-muted">{t.library.emptyStateFiltered}</div>
      ) : (
        <div className="py-10 text-center text-sm text-muted">
          {t.library.emptyStateNoTracks}{" "}
          <Link href="/playlists" className="text-fg underline-offset-4 hover:underline">{t.dashboard.importPlaylist}</Link>{" "}
          {t.library.emptyStateSuffix}
        </div>
      ))}

      {items && items.length > 0 && (view === "list" ? (
      <div className="overflow-x-auto border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-faint">
              <th className={cell}>#</th>
              <th className="whitespace-nowrap">
                <span className={`${cell} flex items-center gap-1.5 uppercase tracking-wide`}>
                  <button
                    type="button"
                    onClick={() => toggleSort("title")}
                    title={t.library.sortColumnHint}
                    className={`inline-flex cursor-pointer select-none items-center gap-1 transition-colors hover:text-fg ${sort === "title" ? "text-fg" : ""}`}
                  >
                    Title{sort === "title" && (order === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                  </button>
                  <span className="text-faint">·</span>
                  <button
                    type="button"
                    onClick={() => toggleSort("artist")}
                    title={t.library.sortColumnHint}
                    className={`inline-flex cursor-pointer select-none items-center gap-1 transition-colors hover:text-fg ${sort === "artist" ? "text-fg" : ""}`}
                  >
                    Artist{sort === "artist" && (order === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                  </button>
                </span>
              </th>
              {th("BPM", "bpm", true)}
              {th("Key", "key")}
              {th("Energy", "energy", true)}
              {th(t.library.colGenre, "genre")}
              {th(t.library.colDuration, "duration", true)}
              {th(t.library.colAdded, "added_at")}
              <th className={cell}>{t.library.colStatus}</th>
              {th(t.tracks.ratingLabel, "rating")}
            </tr>
          </thead>
          <tbody>
            {(items ?? []).map((tr, i) => (
              <tr key={tr.id} className="border-b border-border/50 last:border-0 hover:bg-elevated/40">
                <td className={`${cell} tnum text-faint`}>{String(offset + i + 1).padStart(2, "0")}</td>
                <td className={cell}>
                  <Link href={`/tracks/${tr.id}${trackLinkQuery}`} className="flex items-center gap-2.5">
                    <TrackCover track={tr} className="h-8 w-8" iconSize={14} />
                    <span className="min-w-0">
                      <span className="block max-w-[18rem] truncate font-medium hover:text-fg-strong">{tr.title ?? <span className="italic text-faint">{t.library.untitledTrack}</span>}</span>
                      <span className="block max-w-[18rem] truncate text-xs text-muted">{tr.artist ?? <span className="text-faint">—</span>}</span>
                    </span>
                  </Link>
                </td>
                <td className={`${cell} tnum`}>{tr.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum`}><KeyBadge camelot={tr.camelot_key} /></td>
                <td className={`${cell} tnum text-muted`}>{tr.energy ?? "—"}</td>
                <td className={`${cell} max-w-[10rem] truncate text-muted`}>{tr.genre ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(tr.duration_seconds)}</td>
                <td className={`${cell} whitespace-nowrap text-xs text-muted`}>{fmtDate(tr.added_at)}</td>
                <td className={cell}><TrackStateIcons track={tr} /></td>
                <td className={cell}>
                  <div className="flex items-center justify-end gap-2">
                    <RatingDiamond
                      trackId={tr.id}
                      rating={tr.rating}
                      onSaved={(r) => setItems((cur) => (cur ?? []).map((x) => (x.id === tr.id ? { ...x, rating: r } : x)))}
                    />
                    <button onClick={() => setEditing(tr)} title={t.library.editValuesTitle} className="text-faint transition-colors hover:text-fg-strong"><Pencil size={14} /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      ) : (
        <LibraryTrackGrid tracks={items} onEdit={setEditing} trackLinkQuery={trackLinkQuery} />
      ))}

      {view === "list" && (
        <div className="mt-4 flex items-center justify-between text-sm">
          <span className="text-muted">{total === 0 ? "0" : `${offset + 1}–${Math.min(offset + limit, total)}`} {t.library.paginationOf} {total}</span>
          <div className="flex gap-2">
            <button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - limit))}
              className="inline-flex h-8 items-center gap-1 rounded-none border border-border-strong px-3 hover:bg-elevated disabled:opacity-40"><ChevronLeft size={15} /> {t.library.prevPage}</button>
            <button disabled={offset + limit >= total} onClick={() => setOffset(offset + limit)}
              className="inline-flex h-8 items-center gap-1 rounded-none border border-border-strong px-3 hover:bg-elevated disabled:opacity-40">{t.library.nextPage} <ChevronRight size={15} /></button>
          </div>
        </div>
      )}

      <TrackEditModal
        track={editing}
        open={editing !== null}
        onClose={() => setEditing(null)}
        onSaved={(saved) => setItems((cur) => (cur ?? []).map((x) => (x.id === saved.id ? saved : x)))}
      />
    </PageLayout>
  );
}

export default function Library() {
  return <Suspense><LibraryInner /></Suspense>;
}
