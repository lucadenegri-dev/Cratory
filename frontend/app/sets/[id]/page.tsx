"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useRef, useState } from "react";
import {
  ArrowLeft, Sparkles, Download, Lightbulb, SlidersHorizontal,
  ArrowUp, ArrowDown, Trash2, Replace, Pencil, Check, ChevronDown, Plus, GripVertical,
} from "lucide-react";
import {
  apiGet, apiPost, apiPatch, apiDelete, addTrackToSet, exportSet, fmtDuration, trackLabel,
  type Setlist, type Track, type Alternative, type AlternativeMode, type AlternativesResponse,
} from "@/lib/api";
import { Card, CardHeader, Button, Input, Badge, Alert, Modal, Spinner, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { TrackCover } from "@/components/track-cover";
import { TrackPlayButton } from "@/components/track-play-button";
import { SetArc } from "@/components/set-arc";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

/* Riordino ottimistico: scambio due righe subito, il server poi restituisce la verità
   (con transition_score/mix_tip ricalcolati). */
function swapTracks(s: Setlist, a: number, b: number): Setlist {
  const tracks = s.tracks.map((tr) => ({ ...tr }));
  const ta = tracks.find((tr) => tr.position === a);
  const tb = tracks.find((tr) => tr.position === b);
  if (!ta || !tb) return s;
  ta.position = b;
  tb.position = a;
  tracks.sort((x, y) => x.position - y.position);
  return { ...s, tracks };
}
function dropTrack(s: Setlist, pos: number): Setlist {
  const tracks = s.tracks
    .filter((tr) => tr.position !== pos)
    .map((tr) => (tr.position > pos ? { ...tr, position: tr.position - 1 } : tr));
  return { ...s, tracks };
}
/* Drag-and-drop: sposta la traccia da `from` a `to` (1-based) in un passo, tutte le
   tracce intermedie si riallineano. Ottimistico come swapTracks/dropTrack: il server
   poi restituisce la verità (ruoli/score/note ricalcolati). */
function reorderTrack(s: Setlist, from: number, to: number): Setlist {
  if (from === to) return s;
  const ordered = [...s.tracks].sort((a, b) => a.position - b.position);
  const idx = ordered.findIndex((tr) => tr.position === from);
  if (idx === -1) return s;
  const [item] = ordered.splice(idx, 1);
  ordered.splice(to - 1, 0, item);
  const tracks = ordered.map((tr, i) => ({ ...tr, position: i + 1 }));
  return { ...s, tracks };
}
function slugName(name: string) {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "set";
}

const MODE_KEYS: AlternativeMode[] = ["safer", "softer", "harder", "same_artist", "surprising"];
const MODE_LABEL_KEY: Record<AlternativeMode, "safer" | "softer" | "harder" | "sameArtist" | "surprising"> = {
  safer: "safer",
  softer: "softer",
  harder: "harder",
  same_artist: "sameArtist",
  surprising: "surprising",
};

export default function SetDetail({ params }: { params: Promise<{ id: string }> }) {
  const t = useT();
  const { id } = use(params);
  const router = useRouter();

  const [setlist, setSetlist] = useState<Setlist | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [exported, setExported] = useState<string | null>(null);
  const [playlistUrl, setPlaylistUrl] = useState<string | null>(null);
  const [playlistBusy, setPlaylistBusy] = useState(false);

  const [renameOpen, setRenameOpen] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  // alternative drawer/modal
  const [altPos, setAltPos] = useState<number | null>(null);
  const [altMode, setAltMode] = useState<AlternativeMode>("safer");
  const [altItems, setAltItems] = useState<Alternative[] | null>(null);
  const [altLoading, setAltLoading] = useState(false);

  // aggiungi traccia (A14): ricerca debounced + risultati nel modal
  const [addOpen, setAddOpen] = useState(false);
  const [addQuery, setAddQuery] = useState("");
  const [addResults, setAddResults] = useState<Track[] | null>(null);
  const [addLoading, setAddLoading] = useState(false);

  useEffect(() => {
    apiGet<Setlist>(`/api/sets/${id}`).then(setSetlist).catch((e) => setError(String(e.message ?? e)));
  }, [id]);

  useEffect(() => {
    if (!addOpen) return;
    const timer = setTimeout(() => {
      setAddLoading(true);
      const q = addQuery.trim() || undefined;
      const hasLocalFile = setlist?.owned_only ? "true" : undefined;
      // L'API filtra per titolo O artista separatamente (nessun parametro "q" generico):
      // interroghiamo entrambi e uniamo/dedup lato client per una ricerca titolo-o-artista.
      Promise.all([
        apiGet<{ total: number; items: Track[] }>("/api/tracks", { title: q, has_local_file: hasLocalFile, limit: 10 }),
        q
          ? apiGet<{ total: number; items: Track[] }>("/api/tracks", { artist: q, has_local_file: hasLocalFile, limit: 10 })
          : Promise.resolve({ total: 0, items: [] as Track[] }),
      ])
        .then(([byTitle, byArtist]) => {
          const seen = new Set<number>();
          const merged: Track[] = [];
          for (const tr of [...byTitle.items, ...byArtist.items]) {
            if (seen.has(tr.id)) continue;
            seen.add(tr.id);
            merged.push(tr);
          }
          setAddResults(merged);
        })
        .catch(() => setAddResults([]))
        .finally(() => setAddLoading(false));
    }, 300);
    return () => clearTimeout(timer);
  }, [addOpen, addQuery, setlist?.owned_only]);

  async function reload(p: Promise<Setlist>, opts?: { silent?: boolean }) {
    if (!opts?.silent) setBusy(true);
    setError(null);
    setExported(null);
    try {
      setSetlist(await p);
    } catch (e) {
      setError(String((e as Error).message ?? e));
      // dopo un fallimento su update ottimistico, riallineo alla verità del server
      apiGet<Setlist>(`/api/sets/${id}`).then(setSetlist).catch(() => {});
    } finally {
      if (!opts?.silent) setBusy(false);
    }
  }

  async function loadAlternatives(position: number, mode: AlternativeMode) {
    setAltPos(position);
    setAltMode(mode);
    setAltLoading(true);
    setAltItems(null);
    try {
      const r = await apiPost<AlternativesResponse>(`/api/sets/${id}/alternatives`, { position, mode });
      setAltItems(r.alternatives);
    } catch {
      setAltItems([]);
    } finally {
      setAltLoading(false);
    }
  }

  // Guard leggero: ignoro nuove mutazioni finché la precedente non risponde (niente disabilitazione globale).
  const mutating = useRef(false);

  // Drag-and-drop (B12): posizione trascinata + posizione sorvolata (per l'highlight).
  const [dragPos, setDragPos] = useState<number | null>(null);
  const [overPos, setOverPos] = useState<number | null>(null);

  function move(pos: number, dir: "up" | "down") {
    const target = dir === "up" ? pos - 1 : pos + 1;
    if (mutating.current || !setlist || target < 1 || target > setlist.tracks.length) return;
    mutating.current = true;
    setSetlist((cur) => (cur ? swapTracks(cur, pos, target) : cur)); // ottimistico
    reload(apiPost<Setlist>(`/api/sets/${id}/tracks/${pos}/move`, { direction: dir }), { silent: true })
      .finally(() => { mutating.current = false; });
  }
  function moveToPosition(from: number, to: number) {
    if (mutating.current || !setlist || from === to || from < 1 || to < 1 || to > setlist.tracks.length) return;
    mutating.current = true;
    setSetlist((cur) => (cur ? reorderTrack(cur, from, to) : cur)); // ottimistico
    reload(apiPost<Setlist>(`/api/sets/${id}/tracks/${from}/move`, { to }), { silent: true })
      .finally(() => { mutating.current = false; });
  }
  function remove(pos: number) {
    if (mutating.current || !setlist || setlist.tracks.length <= 1) return;
    mutating.current = true;
    setSetlist((cur) => (cur ? dropTrack(cur, pos) : cur)); // ottimistico
    reload(apiDelete<Setlist>(`/api/sets/${id}/tracks/${pos}`), { silent: true })
      .finally(() => { mutating.current = false; });
  }

  async function doRename() {
    const name = renameValue.trim();
    setRenameOpen(false);
    if (name && name !== setlist?.name) await reload(apiPatch<Setlist>(`/api/sets/${id}`, { name }));
  }

  async function doDelete() {
    setConfirmDelete(false);
    try { await apiDelete(`/api/sets/${id}`); router.push("/sets"); }
    catch (e) { setError(String((e as Error).message ?? e)); }
  }

  async function substitute(alt: Alternative) {
    if (altPos == null) return;
    const pos = altPos;
    setAltPos(null);
    await reload(apiPost<Setlist>(`/api/sets/${id}/tracks/${pos}/replace`, { track_id: alt.track.id }));
  }

  async function addTrack(tr: Track) {
    if (mutating.current || !setlist) return;
    mutating.current = true;
    await reload(addTrackToSet(setlist.id, tr.id)).finally(() => { mutating.current = false; });
  }

  async function doExport(format: "text" | "csv" | "markdown" | "m3u8") {
    if (!setlist) return;
    try {
      const text = await exportSet(setlist.id, format);
      const ext = format === "markdown" ? "md" : format === "csv" ? "csv" : format === "m3u8" ? "m3u8" : "txt";
      const name = `${slugName(setlist.name)}.${ext}`;
      const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
      setExported(name);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }

  async function createPlaylist() {
    if (!setlist) return;
    setPlaylistBusy(true);
    setError(null);
    try {
      const r = await apiPost<{ playlist_url: string }>("/api/spotify/create-playlist", { setlist_id: setlist.id });
      setPlaylistUrl(r.playlist_url);
    } catch (e) { setError(String((e as Error).message ?? e)); } finally { setPlaylistBusy(false); }
  }

  if (error && !setlist) return (
    <PageLayout title={t.sets.pageTitle}>
      <Link href="/sets" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> {t.sets.backLink}</Link>
      <Alert tone="danger">⚠ {error}</Alert>
    </PageLayout>
  );
  if (!setlist) return <PageLayout title={t.sets.pageTitle}><Loading /></PageLayout>;

  const v = setlist.validation ?? {};
  const n = setlist.tracks.length;
  const improvements = v.missing_library_suggestions ?? [];
  const attention = [...(v.critical_points ?? []), ...(v.warnings ?? [])];
  const altTrack = altPos != null ? setlist.tracks.find((st) => st.position === altPos) : null;
  const presentTrackIds = new Set(setlist.tracks.map((st) => st.track.id));
  const addResultsFiltered = addResults?.filter((tr) => !presentTrackIds.has(tr.id)) ?? null;

  const marginalia = (
    <div className="space-y-3">
      <Button variant="outline" size="sm" className="w-full" onClick={() => { setAddQuery(""); setAddResults(null); setAddLoading(true); setAddOpen(true); }}>
        <Plus size={15} /> {t.sets.addTrackButton}
      </Button>
      <div className="grid grid-cols-3 gap-2">
        <Button variant="outline" size="sm" onClick={() => doExport("text")}><Download size={14} /> TXT</Button>
        <Button variant="outline" size="sm" onClick={() => doExport("csv")}>CSV</Button>
        <Button variant="outline" size="sm" onClick={() => doExport("markdown")}>MD</Button>
      </div>
      <Button variant="outline" size="sm" className="w-full" onClick={() => doExport("m3u8")}><Download size={14} /> {t.sets.exportRekordboxButton}</Button>
      <Button variant="outline" size="sm" className="w-full" onClick={createPlaylist} disabled={playlistBusy}>{playlistBusy ? "…" : t.sets.createSpotifyPlaylistButton}</Button>
      <Button variant="danger" size="sm" className="w-full" onClick={() => setConfirmDelete(true)}><Trash2 size={15} /> {t.sets.deleteSetButton}</Button>
      <div className="space-y-2 border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2"><span className="text-muted">{t.sets.tracksLabel}</span><span className="tnum text-fg">{n}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">{t.sets.durationLabel}</span><span className="tnum text-fg">{fmtDuration(setlist.total_duration_seconds)}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">{t.sets.originLabel}</span><span className="text-fg">{setlist.generated_by.includes("ai") ? t.sets.curatedBadge : t.sets.algorithmicBadge}</span></div>
      </div>
    </div>
  );

  return (
    <PageLayout title={t.sets.pageTitle} meta={t.sets.tracksMeta(n)} marginaliaTitle={t.sets.detailsTitle} marginalia={marginalia}>
      <Link href="/sets" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> {t.sets.backLink}</Link>

      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              {setlist.name}
              <Badge tone={setlist.generated_by.includes("ai") ? "primary" : "neutral"}>
                {setlist.generated_by.includes("ai") ? <><Sparkles size={11} /> {t.sets.curatedBadge}</> : t.sets.algorithmicBadge}
              </Badge>
              {setlist.owned_only && <Badge tone="success">{t.sets.ownedOnlyBadge}</Badge>}
              <button
                onClick={() => { setRenameValue(setlist.name); setRenameOpen(true); }}
                title={t.sets.renameTitle} className="text-faint transition-colors hover:text-fg"
              ><Pencil size={14} /></button>
            </span>
          }
          subtitle={`${t.sets.trackCountLabel(n)} · ${fmtDuration(setlist.total_duration_seconds)}${busy ? t.sets.updatingSuffix : ""}`}
        />

        <div className="space-y-4 p-5">
          {error && <Alert tone="danger">⚠ {error}</Alert>}
          {playlistUrl && <Alert tone="info">{t.sets.playlistCreatedPrefix}<a href={playlistUrl} target="_blank" rel="noreferrer" className="underline">{playlistUrl}</a></Alert>}
          {exported && <Alert tone="info">{t.sets.downloadedPrefix}<span className="tnum">{exported}</span></Alert>}

          <SetArc tracks={setlist.tracks} />

          {setlist.global_explanation && (
            <p className="text-sm leading-relaxed text-fg">{setlist.global_explanation}</p>
          )}

          {setlist.curation?.intent_summary && (
            <p className="text-sm leading-relaxed text-fg">
              <strong>{t.sets.compiledIntentTitle}</strong>: {setlist.curation.intent_summary}
            </p>
          )}

          {attention.length > 0 && (
            <div className="border border-danger/50 bg-bg p-3">
              <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-danger">
                <SlidersHorizontal size={14} /> {t.sets.criticalPointsTitle}
              </div>
              <ul className="space-y-1 text-sm text-fg">
                {attention.map((it, i) => <li key={i} className="flex gap-1.5"><span className="shrink-0 text-danger">·</span>{it}</li>)}
              </ul>
            </div>
          )}

          {setlist.mixing_overview.length > 0 && (
            <details className="group border border-border">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted transition-colors hover:text-fg [&::-webkit-details-marker]:hidden">
                <span className="flex items-center gap-1.5"><SlidersHorizontal size={14} /> {t.sets.mixingOverviewTitle}</span>
                <ChevronDown size={15} className="text-faint transition-transform duration-200 group-open:rotate-180" />
              </summary>
              <ul className="space-y-1 border-t border-border p-3 text-sm text-muted">
                {setlist.mixing_overview.map((it, i) => <li key={i} className="flex gap-1.5"><span className="text-faint">·</span>{it}</li>)}
              </ul>
            </details>
          )}

          {improvements.length > 0 && (
            <details className="group border border-border">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted transition-colors hover:text-fg [&::-webkit-details-marker]:hidden">
                <span className="flex items-center gap-1.5"><Lightbulb size={14} /> {t.sets.improvementsTitle}</span>
                <ChevronDown size={15} className="text-faint transition-transform duration-200 group-open:rotate-180" />
              </summary>
              <ul className="space-y-1 border-t border-border p-3 text-sm text-muted">
                {improvements.map((it, i) => <li key={i} className="flex gap-1.5"><span className="text-faint">·</span>{it}</li>)}
              </ul>
            </details>
          )}

          <ol className="space-y-1.5">
            {setlist.tracks.map((st) => (
              <li
                key={st.position}
                onDragOver={(e) => {
                  if (dragPos == null) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                  if (overPos !== st.position) setOverPos(st.position);
                }}
                onDragLeave={() => setOverPos((p) => (p === st.position ? null : p))}
                onDrop={(e) => {
                  e.preventDefault();
                  if (dragPos != null) moveToPosition(dragPos, st.position);
                  setDragPos(null);
                  setOverPos(null);
                }}
                className={cn(
                  "flex items-center gap-3 rounded-none border border-border bg-bg p-3 transition-colors",
                  overPos === st.position && dragPos !== null && dragPos !== st.position && "border-fg-strong bg-elevated",
                  dragPos === st.position && "opacity-50",
                )}
              >
                <span
                  draggable
                  onDragStart={(e) => { setDragPos(st.position); e.dataTransfer.effectAllowed = "move"; }}
                  onDragEnd={() => { setDragPos(null); setOverPos(null); }}
                  title={t.sets.dragHandleTitle}
                  className="cursor-grab touch-none text-faint hover:text-fg active:cursor-grabbing"
                ><GripVertical size={15} /></span>
                <span className="tnum w-5 text-right text-sm text-faint">{st.position}</span>
                <TrackCover track={st.track} className="h-10 w-10" iconSize={16} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    {st.role && <Badge tone="neutral">{st.role}</Badge>}
                    <Link href={`/tracks/${st.track.id}`} className="truncate font-medium hover:text-fg-strong">{trackLabel(st.track)}</Link>
                    <span className="tnum shrink-0 text-xs text-fg">{st.track.bpm?.toFixed(0) ?? "—"} BPM · {st.track.camelot_key ?? "?"} <span className="text-muted">· {fmtDuration(st.track.duration_seconds)}{st.track.genre ? ` · ${st.track.genre}` : ""}</span></span>
                    {st.transition_class && (
                      <Badge tone="neutral">
                        <span title={st.transition_class_reason ?? undefined}>
                          {t.transitionLabels[st.transition_class as keyof typeof t.transitionLabels] ?? st.transition_class}
                        </span>
                      </Badge>
                    )}
                    {(st.mood_tags ?? []).map((tag) => <Badge key={tag} tone="info">{tag}</Badge>)}
                  </div>
                  {st.mix_tip
                    ? <p className="mt-1 flex gap-1.5 text-xs text-fg"><span className="shrink-0 text-faint">↪</span>{st.mix_tip}</p>
                    : <p className="mt-1 text-xs text-muted">{t.sets.openingTrackLabel}</p>}
                </div>
                <div className="flex shrink-0 items-center gap-0.5">
                  <TrackPlayButton track={st.track} className="px-1 text-faint hover:text-fg" />
                  <IconBtn title={t.sets.moveUpTitle} disabled={st.position === 1} onClick={() => move(st.position, "up")}><ArrowUp size={15} /></IconBtn>
                  <IconBtn title={t.sets.moveDownTitle} disabled={st.position === n} onClick={() => move(st.position, "down")}><ArrowDown size={15} /></IconBtn>
                  <IconBtn title={t.sets.alternativesTitle} onClick={() => loadAlternatives(st.position, "safer")}><Replace size={15} /></IconBtn>
                  <IconBtn title={t.sets.removeTitle} danger disabled={n <= 1} onClick={() => remove(st.position)}><Trash2 size={15} /></IconBtn>
                </div>
              </li>
            ))}
          </ol>
        </div>
      </Card>

      {/* Rinomina */}
      <Modal open={renameOpen} onClose={() => setRenameOpen(false)} title={t.sets.renameModalTitle}
        footer={
          <>
            <Button type="button" variant="ghost" size="sm" onClick={() => setRenameOpen(false)}>{t.common.cancel}</Button>
            {/* Fuori dal <form> (il footer della Modal è un fratello del body):
                l'attributo form= lo associa comunque come submit button. */}
            <Button type="submit" form="set-rename-form" size="sm"><Check size={15} /> {t.common.save}</Button>
          </>
        }>
        <form id="set-rename-form" onSubmit={(e) => { e.preventDefault(); void doRename(); }}>
          <Input autoFocus value={renameValue} onChange={(e) => setRenameValue(e.target.value)}
            placeholder={t.sets.setNamePlaceholder} />
        </form>
      </Modal>

      {/* Conferma eliminazione */}
      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title={t.sets.deleteModalTitle}
        footer={<><Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>{t.common.cancel}</Button><Button variant="danger" size="sm" onClick={doDelete}><Trash2 size={15} /> {t.common.delete}</Button></>}>
        <p className="text-sm text-muted">{t.sets.deleteConfirmBody(setlist.name)}</p>
      </Modal>

      {/* Alternative per traccia */}
      <Modal open={altPos != null} onClose={() => setAltPos(null)} size="lg"
        title={<span className="flex items-center gap-2"><Replace size={16} className="text-muted" /> {t.sets.alternativesModalTitle} {altTrack && <span className="truncate text-sm font-normal text-muted">· {trackLabel(altTrack.track)}</span>}</span>}>
        <div className="mb-3 flex flex-wrap gap-1.5">
          {MODE_KEYS.map((key) => (
            <button key={key} aria-pressed={altMode === key} onClick={() => altPos != null && loadAlternatives(altPos, key)}
              className={cn("rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
                altMode === key ? "bg-fg-strong text-bg" : "bg-elevated text-muted hover:text-fg")}>
              {t.sets.modes[MODE_LABEL_KEY[key]]}
            </button>
          ))}
        </div>

        {altLoading && <div className="flex items-center gap-2 py-6 text-sm text-muted"><Spinner /> {t.sets.loadingAlternatives}</div>}
        {!altLoading && altItems && altItems.length === 0 && (
          <p className="py-6 text-center text-sm text-muted">{t.sets.noAlternatives}</p>
        )}
        {!altLoading && altItems && altItems.length > 0 && (
          <ul className="space-y-1.5">
            {altItems.map((a) => (
              <li key={a.track.id} className="flex items-center gap-3 rounded-none border border-border bg-bg p-2.5">
                <TrackCover track={a.track} className="h-9 w-9" iconSize={15} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2">
                    <span className="truncate text-sm font-medium">{trackLabel(a.track)}</span>
                    <span className="tnum shrink-0 text-xs text-fg">{a.track.bpm?.toFixed(0) ?? "—"} · {a.track.camelot_key ?? "?"}</span>
                    <Badge tone="neutral">{a.risk_level}</Badge>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted">{a.reason}
                    <span className="tnum text-faint"> · {t.sets.altScorePrev} {a.score_prev ?? "—"}{a.score_next != null && t.sets.altScoreNext(a.score_next)}</span>
                  </p>
                </div>
                <Button size="sm" variant="outline" onClick={() => substitute(a)}><Check size={14} /> {t.sets.useAlternativeButton}</Button>
              </li>
            ))}
          </ul>
        )}
      </Modal>

      {/* Aggiungi traccia (A14) */}
      <Modal open={addOpen} onClose={() => setAddOpen(false)} size="lg"
        title={<span className="flex items-center gap-2"><Plus size={16} className="text-muted" /> {t.sets.addTrackModalTitle}</span>}>
        <Input autoFocus className="mb-3" value={addQuery} onChange={(e) => setAddQuery(e.target.value)}
          placeholder={t.sets.addTrackSearchPlaceholder} />

        {addLoading && <div className="flex items-center gap-2 py-6 text-sm text-muted"><Spinner /> {t.common.loading}</div>}
        {!addLoading && addResultsFiltered && addResultsFiltered.length === 0 && (
          <p className="py-6 text-center text-sm text-muted">{t.sets.addTrackNoResults}</p>
        )}
        {!addLoading && addResultsFiltered && addResultsFiltered.length > 0 && (
          <ul className="space-y-1.5">
            {addResultsFiltered.map((tr) => (
              <li key={tr.id} className="flex items-center gap-3 rounded-none border border-border bg-bg p-2.5">
                <TrackCover track={tr} className="h-9 w-9" iconSize={15} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2">
                    <span className="truncate text-sm font-medium">{trackLabel(tr)}</span>
                    <span className="tnum shrink-0 text-xs text-fg">{tr.bpm?.toFixed(0) ?? "—"} · {tr.camelot_key ?? "?"}</span>
                    {tr.has_local_file && <Badge tone="success">{t.transitions.hasFileBadge}</Badge>}
                  </div>
                </div>
                <Button size="sm" variant="outline" onClick={() => addTrack(tr)}><Plus size={14} /> {t.sets.addTrackAddButton}</Button>
              </li>
            ))}
          </ul>
        )}
      </Modal>
    </PageLayout>
  );
}

function IconBtn({ title, onClick, disabled, danger, children }: {
  title: string; onClick: () => void; disabled?: boolean; danger?: boolean; children: React.ReactNode;
}) {
  return (
    <button title={title} onClick={onClick} disabled={disabled}
      className={cn(
        "grid h-8 w-8 place-items-center rounded-none text-faint transition-colors hover:bg-elevated hover:text-fg disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-faint",
        danger && "hover:bg-danger/15 hover:text-danger",
      )}>
      {children}
    </button>
  );
}
