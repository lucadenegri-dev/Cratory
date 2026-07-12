"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Pencil, List, LayoutGrid } from "lucide-react";
import { apiGet, fmtDuration, type Track } from "@/lib/api";
import { Input, Select, Checkbox, Alert, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { TrackEditModal } from "@/components/track-edit-modal";
import { TrackCover } from "@/components/track-cover";
import { TrackStateIcons } from "@/components/track-state-icons";
import { KeyBadge } from "@/components/key-badge";
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
  const [offset, setOffset] = useState(0);
  const PAGE_SIZE = 50;

  const [artist, setArtist] = useState("");
  const [title, setTitle] = useState("");
  // Filtro genere pre-impostato via query param (es. link "Generi" dalla dashboard).
  // useSearchParams() è coerente fra SSR e client (niente hydration mismatch) e resta
  // reattivo se il param cambia mentre si è già sulla pagina.
  const genreParam = useSearchParams().get("genre") ?? "";
  const [genre, setGenre] = useState(genreParam);
  useEffect(() => { setGenre(genreParam); setOffset(0); }, [genreParam]);
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [bpmMin, setBpmMin] = useState("");
  const [bpmMax, setBpmMax] = useState("");
  const [key, setKey] = useState("");
  const [incomplete, setIncomplete] = useState(false);
  const [owned, setOwned] = useState(""); // "" = tutte | "true" = possedute | "false" = wishlist
  const [sort, setSort] = useState("");
  const [order, setOrder] = useState<Order>("asc");
  const [editing, setEditing] = useState<Track | null>(null);
  const [view, setView] = useState<"list" | "grid">("list");
  // Griglia: nessuna paginazione, si caricano tutte le tracce (limit=0 = "tutte" lato API).
  const limit = view === "grid" ? 0 : PAGE_SIZE;
  // Cambio vista: riparti da capo (in griglia l'offset non è usato).
  useEffect(() => { setOffset(0); }, [view]);
  // Persistenza: letta solo lato client (mai in render/SSR) per non rompere l'hydration.
  useEffect(() => {
    const saved = localStorage.getItem("cratory:library:view");
    if (saved === "grid" || saved === "list") setView(saved);
  }, []);
  useEffect(() => {
    localStorage.setItem("cratory:library:view", view);
  }, [view]);

  const load = useCallback(() => {
    apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      artist, title, genre, source, status, bpm_min: bpmMin, bpm_max: bpmMax, key,
      incomplete_metadata: incomplete ? true : undefined,
      has_local_file: owned || undefined,
      sort: sort || undefined, order: sort ? order : undefined,
      limit, offset,
    })
      .then((r) => { setItems(r.items); setTotal(r.total); setError(null); })
      .catch((e) => setError(String(e.message ?? e)));
  }, [artist, title, genre, source, status, bpmMin, bpmMax, key, incomplete, owned, sort, order, offset, view]);

  useEffect(() => { const timer = setTimeout(load, 250); return () => clearTimeout(timer); }, [load]);

  const cell = "px-3 py-2.5";

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
    artist || title || genre || source || status || bpmMin || bpmMax || key || incomplete || owned
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
              {th("Title", "title")}
              {th("Artist", "artist")}
              {th("BPM", "bpm", true)}
              {th("Key", "key")}
              {th("Energy", "energy", true)}
              {th(t.library.colGenre, "genre")}
              {th(t.library.colDuration, "duration", true)}
              <th className={cell}>{t.library.colStatus}</th>
              <th className={cell}></th>
            </tr>
          </thead>
          <tbody>
            {(items ?? []).map((tr, i) => (
              <tr key={tr.id} className="border-b border-border/50 last:border-0 hover:bg-elevated/40">
                <td className={`${cell} tnum text-faint`}>{String(offset + i + 1).padStart(2, "0")}</td>
                <td className={cell}>
                  <Link href={`/tracks/${tr.id}`} className="flex items-center gap-2.5">
                    <TrackCover track={tr} className="h-8 w-8" iconSize={14} />
                    <span className="max-w-[16rem] truncate font-medium hover:text-fg-strong">{tr.title ?? <span className="italic text-faint">{t.library.untitledTrack}</span>}</span>
                  </Link>
                </td>
                <td className={`${cell} text-muted`}>{tr.artist ?? <span className="text-faint">—</span>}</td>
                <td className={`${cell} tnum`}>{tr.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum`}><KeyBadge camelot={tr.camelot_key} /></td>
                <td className={`${cell} tnum text-muted`}>{tr.energy ?? "—"}</td>
                <td className={`${cell} max-w-[10rem] truncate text-muted`}>{tr.genre ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(tr.duration_seconds)}</td>
                <td className={cell}><TrackStateIcons track={tr} /></td>
                <td className={cell}>
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => setEditing(tr)} title={t.library.editValuesTitle} className="text-faint transition-colors hover:text-fg-strong"><Pencil size={14} /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      ) : (
        <LibraryTrackGrid tracks={items} onEdit={setEditing} />
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
