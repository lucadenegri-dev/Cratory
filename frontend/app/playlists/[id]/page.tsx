"use client";

import Link from "next/link";
import { Suspense, use, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import {
  ArrowLeft, ExternalLink, AlertTriangle, Info, Trash2, Sparkles, Pencil,
  RefreshCw, ChevronUp, ChevronDown, ChevronLeft, ChevronRight, Download, Heart,
} from "lucide-react";
import {
  getPlaylist, playlistTracks, playlistGaps, deletePlaylist, syncPlaylist, errText, fmtDuration,
  startPlaylistDownload, removeTrackFromPlaylist, exportPlaylist, reorderPlaylistTrack,
  type Playlist, type Track, type GapAnalysis,
} from "@/lib/api";
import { useBackLink, withFrom } from "@/lib/back-link";
import { Card, Badge, Alert, Button, Spinner, Input, Select, Checkbox, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { ButtonLink } from "@/components/button-link";
import { TrackCover } from "@/components/track-cover";
import { PlaylistCover } from "@/components/playlist-cover";
import { useJobs } from "@/components/jobs-provider";
import { TrackEditModal } from "@/components/track-edit-modal";
import { ConfirmModal } from "@/components/confirm-modal";
import { KeyBadge } from "@/components/key-badge";
import { TrackStateIcons } from "@/components/track-state-icons";
import { useT, translateGap } from "@/lib/i18n";

type Order = "asc" | "desc";

function slugName(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "playlist";
}

// Ordinamento Camelot: prima il numero (1..12), poi la lettera (A prima di B).
function camelotRank(key: string | null): number {
  const m = key ? /^\s*(\d{1,2})\s*([ABab])\s*$/.exec(key) : null;
  if (!m) return Number.POSITIVE_INFINITY;
  return Number(m[1]) * 2 + (m[2].toUpperCase() === "B" ? 1 : 0);
}

function PlaylistDetailInner({ params }: { params: Promise<{ id: string }> }) {
  const t = useT();
  const STATUS_OPTIONS: [string, string][] = [
    ["ready_for_set", t.library.statusReadyOption],
    ["imported", t.library.statusImportedOption],
  ];
  const { id } = use(params);
  const pid = Number(id);
  const router = useRouter();
  // Alla playlist si arriva dalla lista, da Shazam e dalla wishlist: si torna
  // dove eri, non sempre all'elenco.
  const back = useBackLink({ href: "/playlists", labelKey: "playlists" });
  const from = usePathname();
  const [downloading, setDownloading] = useState(false);
  const jobs = useJobs();
  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [gaps, setGaps] = useState<GapAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [editing, setEditing] = useState<Track | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmRemoveTrack, setConfirmRemoveTrack] = useState<Track | null>(null);
  const [removingTrackId, setRemovingTrackId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);

  // Filtri (come in libreria) — applicati lato client sulla playlist (insieme limitato).
  const [artist, setArtist] = useState("");
  const [title, setTitle] = useState("");
  const [genre, setGenre] = useState("");
  const [source, setSource] = useState("");
  const [status, setStatus] = useState("");
  const [bpmMin, setBpmMin] = useState("");
  const [bpmMax, setBpmMax] = useState("");
  const [key, setKey] = useState("");
  const [owned, setOwned] = useState(""); // "" = tutte | "true" = possedute | "false" = wishlist
  const [incomplete, setIncomplete] = useState(false);
  const [sort, setSort] = useState("");
  const [order, setOrder] = useState<Order>("asc");
  const PAGE_SIZE = 50;
  const [page, setPage] = useState(0);

  // Riordino manuale della colonna "#": disponibile su tutte le playlist manuali,
  // anche con un ordinamento per colonna attivo (agisce sull'ordine della playlist,
  // non sulla vista ordinata).
  const canReorder = playlist?.kind === "manual";
  const [editingRank, setEditingRank] = useState<number | null>(null); // id traccia in modifica
  const [reordering, setReordering] = useState(false);

  const reload = useCallback((signal?: AbortSignal) => {
    playlistTracks(pid, { signal }).then(setTracks).catch(() => {});
    playlistGaps(pid, { signal }).then(setGaps).catch(() => {});
  }, [pid]);

  useEffect(() => {
    const ac = new AbortController();
    getPlaylist(pid, { signal: ac.signal }).then(setPlaylist)
      .catch((e) => { if (e?.name !== "AbortError") setError(errText(e)); });
    reload(ac.signal);
    return () => ac.abort();
  }, [pid, reload]);

  // Rank di posizione: indice nell'array `tracks`, che arriva già in ordine
  // `position` dal backend (manuale-riordinabile o cronologico per le altre
  // playlist). Resta legato alla traccia anche quando si ordina/filtra per
  // un'altra colonna.
  const insertionRank = useMemo(() => {
    const map = new Map<number, number>();
    tracks.forEach((tr, i) => map.set(tr.id, i + 1));
    return map;
  }, [tracks]);

  const visible = useMemo(() => {
    const inc = (v: string | null, q: string) => (v ?? "").toLowerCase().includes(q.toLowerCase());
    let rows = tracks.filter((tr) => {
      if (artist && !inc(tr.artist, artist)) return false;
      if (title && !inc(tr.title, title)) return false;
      if (genre && !inc(tr.genre, genre)) return false;
      if (source && tr.source_type !== source) return false;
      if (status && tr.status !== status) return false;
      if (owned && tr.has_local_file !== (owned === "true")) return false;
      if (key && !inc(tr.camelot_key, key)) return false;
      if (bpmMin && (tr.bpm ?? -Infinity) < Number(bpmMin)) return false;
      if (bpmMax && (tr.bpm ?? Infinity) > Number(bpmMax)) return false;
      if (incomplete && tr.bpm != null && tr.camelot_key != null && tr.title != null && tr.artist != null) return false;
      return true;
    });

    const dir = order === "asc" ? 1 : -1;
    const num = (v: number | null) => (v == null ? (order === "asc" ? Infinity : -Infinity) : v);
    const str = (v: string | null) => (v ?? "").toLowerCase();
    const getters: Record<string, (tr: Track) => number | string> = {
      rank: (tr) => insertionRank.get(tr.id) ?? 0,
      title: (tr) => str(tr.title), artist: (tr) => str(tr.artist), source: (tr) => tr.source_type,
      bpm: (tr) => num(tr.bpm), key: (tr) => camelotRank(tr.camelot_key), energy: (tr) => num(tr.energy),
      genre: (tr) => str(tr.genre), duration: (tr) => num(tr.duration_seconds), status: (tr) => tr.status,
    };
    if (sort && getters[sort]) {
      const g = getters[sort];
      rows = [...rows].sort((a, b) => { const x = g(a), y = g(b); return x < y ? -dir : x > y ? dir : 0; });
    } else {
      // ordine di default = ordine di inserimento
      rows = [...rows].sort((a, b) => (insertionRank.get(a.id) ?? 0) - (insertionRank.get(b.id) ?? 0));
    }
    return rows;
  }, [tracks, artist, title, genre, source, status, owned, key, bpmMin, bpmMax, incomplete, sort, order, insertionRank]);

  // Paginazione lato client sull'insieme già filtrato/ordinato: si riparte da pagina 0
  // ogni volta che cambia un filtro (stesso pattern della libreria).
  useEffect(() => {
    setPage(0);
  }, [artist, title, genre, source, status, owned, key, bpmMin, bpmMax, incomplete]);

  const pageCount = Math.max(1, Math.ceil(visible.length / PAGE_SIZE));
  // Clamp difensivo: se la lista si accorcia (sync, edit) sotto la pagina corrente.
  const safePage = Math.min(page, pageCount - 1);
  const pageTracks = visible.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  const toggleSort = (col: string) => {
    if (sort === col) setOrder(order === "asc" ? "desc" : "asc");
    else { setSort(col); setOrder("asc"); }
    setPage(0);
  };

  const doDelete = async () => {
    if (!playlist) return;
    setDeleting(true);
    try {
      await deletePlaylist(pid);
      router.push("/playlists");
    } catch (e) {
      setError(String((e as Error).message ?? e));
      setDeleting(false);
    }
  };

  const doSync = async () => {
    setSyncing(true);
    setSyncMsg(null);
    setError(null);
    try {
      await syncPlaylist(pid);
      // Il sync gira in background (barra job globale): l'esito arriva
      // nell'effect sotto quando il job passa running -> done.
      jobs.refresh();
      setSyncMsg(t.playlists.syncStartedNote);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setSyncing(false);
    }
  };

  // Sync streaming in background: quando il job finisce (running -> done) i
  // dati di questa playlist sono stantii, ricarica in automatico (stesso
  // pattern di /analysis con jobs.analysis).
  const prevSyncStatus = useRef<string | null>(null);
  useEffect(() => {
    const status = jobs.streamingImport?.status ?? null;
    if (prevSyncStatus.current === "running") {
      if (status === "done") {
        const result = jobs.streamingImport?.result;
        setSyncMsg(result ? t.playlists.syncSummary(result.created, result.removed, result.total) : null);
        getPlaylist(pid).then(setPlaylist).catch(() => {});
        reload();
      } else if (status === "error") {
        setError(jobs.streamingImport?.error ?? null);
      }
    }
    prevSyncStatus.current = status;
  }, [jobs.streamingImport?.status, jobs.streamingImport?.result, jobs.streamingImport?.error, pid, reload, t]);

  if (error) return (
    <PageLayout title={t.playlists.pageTitle}>
      <Link href={back.href} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> {back.label}</Link>
      <Alert tone="danger">⚠ {error}</Alert>
    </PageLayout>
  );
  if (!playlist) return <PageLayout title={t.playlists.pageTitle}><Loading /></PageLayout>;

  const ready = tracks.filter((tr) => tr.status === "ready_for_set").length;
  const ownedCount = tracks.filter((tr) => tr.has_local_file).length;
  const missing = tracks.filter((tr) => !tr.has_local_file && !tr.archived).length;
  const totalDur = tracks.reduce((s, tr) => s + (tr.duration_seconds ?? 0), 0);
  const cell = "px-3 py-2.5";
  const canSync =
    (playlist.platform === "spotify" && (playlist.kind === "liked" || !!playlist.platform_playlist_id)) ||
    (playlist.platform === "soundcloud" && playlist.kind !== "liked" && !!playlist.url);
  const platformName = playlist.platform === "soundcloud" ? "SoundCloud" : "Spotify";
  const likedImportHref = playlist.platform === "soundcloud" ? "/playlists/import-soundcloud/likes" : "/playlists/import-spotify/liked";

  const th = (label: string, col: string, numeric = false) => {
    const active = sort === col;
    return (
      <th
        onClick={() => toggleSort(col)}
        title={t.library.sortColumnHint}
        className={`${cell} ${numeric ? "tnum " : ""}cursor-pointer select-none whitespace-nowrap transition-colors hover:text-fg ${active ? "text-fg" : ""}`}
      >
        <span className="inline-flex items-center gap-1">
          {label}
          {active && (order === "asc" ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
        </span>
      </th>
    );
  };

  const doDownloadMissing = async () => {
    setDownloading(true);
    try {
      await startPlaylistDownload(pid);
      jobs.refresh(); // si resta qui: il progresso vive nella barra job in basso
    } catch (e) {
      setError(t.playlists.downloadNotStarted(String((e as Error).message ?? e)));
    } finally {
      setDownloading(false);
    }
  };

  const doRemoveTrack = async (tr: Track) => {
    setActionError(null);
    setNotice(null);
    setRemovingTrackId(tr.id);
    const label = tr.title ?? tr.artist ?? String(tr.id);
    try {
      const { deleted_tracks } = await removeTrackFromPlaylist(pid, tr.id);
      setTracks((cur) => cur.filter((x) => x.id !== tr.id));
      setPlaylist((p) => (p ? { ...p, track_count: Math.max(0, p.track_count - 1) } : p));
      setNotice(deleted_tracks > 0 ? t.playlists.trackRemovedWithLead(label) : t.playlists.trackRemoved(label));
    } catch (e) {
      setActionError(t.playlists.removeTrackFailed(errText(e)));
    } finally {
      setRemovingTrackId(null);
    }
  };

  const applyReorder = async (trackId: number, position: number) => {
    setEditingRank(null);
    setActionError(null);
    setReordering(true);
    try {
      const rows = await reorderPlaylistTrack(pid, trackId, position);
      setTracks(rows);
    } catch (e) {
      setActionError(t.playlists.reorderFailed(errText(e)));
    } finally {
      setReordering(false);
    }
  };

  const doExport = async () => {
    if (!playlist) return;
    setActionError(null);
    setExporting(true);
    try {
      const body = await exportPlaylist(pid);
      const url = URL.createObjectURL(new Blob([body], { type: "audio/x-mpegurl" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = `${slugName(playlist.name)}.m3u8`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setActionError(t.playlists.exportFailed(errText(e)));
    } finally {
      setExporting(false);
    }
  };

  const marginalia = (
    <div className="space-y-3">
      <ButtonLink href={`/set-builder?playlist=${pid}`} size="sm" block><Sparkles size={15} /> {t.playlists.buildSetButton}</ButtonLink>
      {missing > 0 && (
        <Button size="sm" variant="outline" className="w-full" onClick={doDownloadMissing} disabled={downloading}>
          {downloading ? <Spinner /> : <Download size={15} />} {t.playlists.downloadMissingButton(missing)}
        </Button>
      )}
      {playlist.kind === "liked"
        ? <ButtonLink href={likedImportHref} size="sm" variant="outline" block><Heart size={14} /> {t.playlists.addMoreLiked}</ButtonLink>
        : canSync && <Button size="sm" variant="outline" className="w-full" onClick={doSync} disabled={syncing}>{syncing ? <Spinner /> : <RefreshCw size={14} />} {t.playlists.syncFromButton(platformName)}</Button>}
      {playlist.url && <a href={playlist.url} target="_blank" rel="noreferrer" className="block"><Button size="sm" variant="outline" className="w-full"><ExternalLink size={14} /> {platformName}</Button></a>}
      <Button size="sm" variant="outline" className="w-full" onClick={doExport} disabled={exporting}>{exporting ? <Spinner /> : <Download size={15} />} {t.playlists.exportRekordboxButton}</Button>
      <Button size="sm" variant="danger" className="w-full" onClick={() => setConfirmDelete(true)} disabled={deleting}>{deleting ? <Spinner /> : <Trash2 size={15} />} {t.playlists.removeButton}</Button>
      <div className="space-y-2 border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2"><span className="text-muted">{t.playlists.statTracksLabel}</span><span className="tnum text-fg">{playlist.track_count}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">{t.playlists.statReadyLabel}</span><span className="tnum text-fg">{ready}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">{t.playlists.statDurationLabel}</span><span className="tnum text-fg">{fmtDuration(totalDur)}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">{t.playlists.statOwnerLabel}</span><span className="truncate text-fg">{playlist.owner ?? "—"}</span></div>
      </div>
    </div>
  );

  return (
    <PageLayout title={t.playlists.pageTitle} meta={playlist.name} marginaliaTitle={t.playlists.marginaliaDetails} marginalia={marginalia}>
      <Link href={back.href} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> {back.label}</Link>

      <div className="mb-6 flex flex-wrap items-start gap-4">
        <PlaylistCover artworkUrl={playlist.artwork_url} platform={playlist.platform} kind={playlist.kind} className="h-24 w-24" iconSize={30} placeholderClassName="bg-surface-2" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{playlist.name}</h1>
            <Badge tone="neutral">{playlist.platform}</Badge>
            {playlist.kind === "liked" && <Badge tone="neutral">liked</Badge>}
          </div>
          <p className="mt-1 text-sm text-muted">{t.playlists.trackCount(playlist.track_count)} · {t.playlists.readyForSetLabel(ready)} · {t.playlists.ownedOfLabel(ownedCount, tracks.length)} · {fmtDuration(totalDur)}{playlist.owner ? ` · ${playlist.owner}` : ""}</p>
        </div>
      </div>

      {syncMsg && <div className="mb-4"><Alert tone="info">{t.playlists.syncedPrefix}{syncMsg}</Alert></div>}
      {notice && <div className="mb-4"><Alert tone="info">{notice}</Alert></div>}
      {actionError && <div className="mb-4"><Alert tone="danger">⚠ {actionError}</Alert></div>}

      {gaps && gaps.gaps.length > 0 && (
        <details className="group mb-4 border border-border">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-muted transition-colors hover:text-fg [&::-webkit-details-marker]:hidden">
            <span>{t.playlists.tipsHeading(gaps.gaps.length)}</span>
            <ChevronDown size={15} className="text-faint transition-transform duration-200 group-open:rotate-180" />
          </summary>
          <div className="grid gap-2 border-t border-border p-4">
            {gaps.gaps.map((g) => {
              const { description, suggestion } = translateGap(g.gap_type, g.params, g);
              return (
                <div key={g.gap_type} className="flex gap-2 text-sm">
                  {g.severity === "warning"
                    ? <AlertTriangle size={15} className="mt-0.5 shrink-0 text-muted" />
                    : <Info size={15} className="mt-0.5 shrink-0 text-muted" />}
                  <div><span className="text-fg">{description}</span> <span className="text-muted">{suggestion}</span></div>
                </div>
              );
            })}
          </div>
        </details>
      )}

      <Card className="mb-4">
        <div className="p-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            <Input className="h-9" placeholder={t.library.filterArtistPlaceholder} value={artist} onChange={(e) => setArtist(e.target.value)} />
            <Input className="h-9" placeholder={t.library.filterTitlePlaceholder} value={title} onChange={(e) => setTitle(e.target.value)} />
            <Input className="h-9" placeholder={t.library.filterGenrePlaceholder} value={genre} onChange={(e) => setGenre(e.target.value)} />
            <Select className="h-9" value={source} onChange={(e) => setSource(e.target.value)}>
              <option value="">{t.library.sourceAllOption}</option>
              <option value="spotify">Spotify</option>
              <option value="soundcloud">SoundCloud</option>
              <option value="manual">{t.library.sourceManualOption}</option>
            </Select>
            <Select className="h-9" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">{t.library.statusAllOption}</option>
              {STATUS_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </Select>
            <Select className="h-9" value={owned} onChange={(e) => setOwned(e.target.value)}>
              <option value="">{t.library.ownedAllOption}</option>
              <option value="true">{t.library.ownedTrueOption}</option>
              <option value="false">{t.library.ownedFalseOption}</option>
            </Select>
            <Input className="h-9" type="number" placeholder={t.library.bpmMinPlaceholder} value={bpmMin} onChange={(e) => setBpmMin(e.target.value)} />
            <Input className="h-9" type="number" placeholder={t.library.bpmMaxPlaceholder} value={bpmMax} onChange={(e) => setBpmMax(e.target.value)} />
            <Input className="h-9" placeholder={t.library.keyPlaceholder} value={key} onChange={(e) => setKey(e.target.value)} />
          </div>
          <div className="mt-2"><Checkbox label={t.playlists.incompleteOnlyLabel} checked={incomplete} onChange={setIncomplete} /></div>
        </div>
      </Card>

      <div className="overflow-x-auto border border-border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-faint">
              {th("#", "rank", true)}
              {th("Title", "title")}
              {th("Artist", "artist")}
              {th(t.library.colGenre, "genre")}
              {th("BPM", "bpm", true)}
              {th("Key", "key")}
              {th(t.library.colEnergy, "energy", true)}
              {th(t.library.colDuration, "duration", true)}
              <th className={cell}>{t.library.colStatus}</th>
              <th className={cell}></th>
            </tr>
          </thead>
          <tbody>
            {pageTracks.map((tr) => (
              <tr key={tr.id} className="border-b border-border/50 last:border-0 hover:bg-elevated/40">
                <td className={`${cell} tnum text-faint`}>
                  {canReorder ? (
                    editingRank === tr.id ? (
                      <input
                        type="number"
                        min={1}
                        max={tracks.length}
                        defaultValue={insertionRank.get(tr.id) ?? 1}
                        autoFocus
                        disabled={reordering}
                        aria-label={t.playlists.reorderPositionAria}
                        onBlur={() => setEditingRank(null)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") {
                            const v = Number((e.target as HTMLInputElement).value);
                            if (Number.isFinite(v) && v >= 1) applyReorder(tr.id, v);
                          } else if (e.key === "Escape") setEditingRank(null);
                        }}
                        className="w-12 border border-border bg-bg px-1 py-0.5 text-right text-xs tnum"
                      />
                    ) : (
                      <button
                        type="button"
                        onClick={() => setEditingRank(tr.id)}
                        disabled={reordering}
                        className="tnum hover:text-fg"
                        title={t.playlists.editPositionTitle}
                      >
                        {insertionRank.get(tr.id) ?? "—"}
                      </button>
                    )
                  ) : (
                    insertionRank.get(tr.id) ?? "—"
                  )}
                </td>
                <td className={cell}>
                  <Link href={withFrom(`/tracks/${tr.id}`, from)} className="flex items-center gap-2.5">
                    <TrackCover track={tr} className="h-8 w-8" iconSize={14} />
                    <span className="max-w-[16rem] truncate font-medium hover:text-fg-strong">{tr.title ?? <span className="italic text-faint">{t.library.untitledTrack}</span>}</span>
                  </Link>
                </td>
                <td className={`${cell} text-muted`}>{tr.artist ?? "—"}</td>
                <td className={`${cell} max-w-[10rem] truncate text-muted`}>{tr.genre ?? "—"}</td>
                <td className={`${cell} tnum`}>{tr.bpm?.toFixed(0) ?? "—"}</td>
                <td className={`${cell} tnum`}><KeyBadge camelot={tr.camelot_key} /></td>
                <td className={`${cell} tnum text-muted`}>{tr.energy ?? "—"}</td>
                <td className={`${cell} tnum text-muted`}>{fmtDuration(tr.duration_seconds)}</td>
                <td className={cell}><TrackStateIcons track={tr} /></td>
                <td className={cell}>
                  <div className="flex items-center justify-end gap-2">
                    <button onClick={() => setEditing(tr)} title={t.library.editValuesTitle} className="text-faint transition-colors hover:text-fg-strong"><Pencil size={14} /></button>
                    <button onClick={() => setConfirmRemoveTrack(tr)} disabled={removingTrackId !== null} title={t.playlists.removeTrackTitle} className="text-faint transition-colors hover:text-danger disabled:opacity-40">
                      {removingTrackId === tr.id ? <Spinner /> : <Trash2 size={14} />}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {visible.length === 0 && <tr><td colSpan={10} className="px-3 py-10 text-center text-sm text-muted">{t.library.emptyStatePrefix}</td></tr>}
          </tbody>
        </table>
      </div>

      {visible.length > 0 && (
        <div className="mt-4 flex items-center justify-between text-sm">
          <span className="text-muted">
            {`${safePage * PAGE_SIZE + 1}–${Math.min((safePage + 1) * PAGE_SIZE, visible.length)}`} {t.library.paginationOf} {visible.length}
          </span>
          <div className="flex gap-2">
            <button disabled={safePage === 0} onClick={() => setPage(Math.max(0, safePage - 1))}
              className="inline-flex h-8 items-center gap-1 rounded-none border border-border-strong px-3 hover:bg-elevated disabled:opacity-40"><ChevronLeft size={15} /> {t.library.prevPage}</button>
            <button disabled={safePage + 1 >= pageCount} onClick={() => setPage(safePage + 1)}
              className="inline-flex h-8 items-center gap-1 rounded-none border border-border-strong px-3 hover:bg-elevated disabled:opacity-40">{t.library.nextPage} <ChevronRight size={15} /></button>
          </div>
        </div>
      )}

      <TrackEditModal
        track={editing}
        open={editing !== null}
        onClose={() => setEditing(null)}
        onSaved={(tr) => setTracks((cur) => cur.map((x) => (x.id === tr.id ? tr : x)))}
      />

      <ConfirmModal
        open={confirmDelete}
        title={t.common.delete}
        message={t.playlists.detailDeleteConfirm(playlist.name)}
        tone="danger"
        confirmLabel={t.common.delete}
        onConfirm={() => { setConfirmDelete(false); doDelete(); }}
        onClose={() => setConfirmDelete(false)}
      />

      <ConfirmModal
        open={confirmRemoveTrack !== null}
        title={t.playlists.removeTrackTitle}
        message={confirmRemoveTrack ? t.playlists.removeTrackConfirm(confirmRemoveTrack.title ?? confirmRemoveTrack.artist ?? String(confirmRemoveTrack.id)) : ""}
        tone="danger"
        confirmLabel={t.common.delete}
        onConfirm={() => {
          const tr = confirmRemoveTrack;
          setConfirmRemoveTrack(null);
          if (tr) doRemoveTrack(tr);
        }}
        onClose={() => setConfirmRemoveTrack(null)}
      />
    </PageLayout>
  );
}

export default function PlaylistDetail(props: { params: Promise<{ id: string }> }) {
  return <Suspense><PlaylistDetailInner {...props} /></Suspense>;
}
