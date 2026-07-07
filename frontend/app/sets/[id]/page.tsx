"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import {
  ArrowLeft, Sparkles, Download, Lightbulb, SlidersHorizontal,
  ArrowUp, ArrowDown, Trash2, Replace, Pencil, Check, ChevronDown,
} from "lucide-react";
import {
  apiGet, apiPost, apiPatch, apiDelete, exportSet, fmtDuration, trackLabel,
  type Setlist, type Alternative, type AlternativeMode, type AlternativesResponse,
} from "@/lib/api";
import { Card, CardHeader, Button, Input, Badge, Alert, Modal, Spinner, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { TrackCover } from "@/components/track-cover";
import { cn } from "@/lib/cn";

const MODES: { key: AlternativeMode; label: string }[] = [
  { key: "safer", label: "Più sicura" },
  { key: "softer", label: "Più morbida" },
  { key: "harder", label: "Più dura" },
  { key: "same_artist", label: "Stesso artista" },
  { key: "surprising", label: "Sorprendente" },
];

export default function SetDetail({ params }: { params: Promise<{ id: string }> }) {
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

  useEffect(() => {
    apiGet<Setlist>(`/api/sets/${id}`).then(setSetlist).catch((e) => setError(String(e.message ?? e)));
  }, [id]);

  async function reload(p: Promise<Setlist>) {
    setBusy(true);
    setError(null);
    setExported(null);
    try { setSetlist(await p); } catch (e) { setError(String((e as Error).message ?? e)); } finally { setBusy(false); }
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

  const move = (pos: number, dir: "up" | "down") =>
    reload(apiPost<Setlist>(`/api/sets/${id}/tracks/${pos}/move`, { direction: dir }));
  const remove = (pos: number) => reload(apiDelete<Setlist>(`/api/sets/${id}/tracks/${pos}`));

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

  async function doExport(format: "text" | "csv" | "markdown") {
    if (!setlist) return;
    setExported(await exportSet(setlist.id, format));
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
    <PageLayout title="Set">
      <Link href="/sets" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Set</Link>
      <Alert tone="danger">⚠ {error}</Alert>
    </PageLayout>
  );
  if (!setlist) return <PageLayout title="Set"><Loading /></PageLayout>;

  const v = setlist.validation ?? {};
  const n = setlist.tracks.length;
  const improvements = v.missing_library_suggestions ?? [];
  const altTrack = altPos != null ? setlist.tracks.find((st) => st.position === altPos) : null;

  const marginalia = (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <Button variant="outline" size="sm" onClick={() => doExport("text")}><Download size={14} /> TXT</Button>
        <Button variant="outline" size="sm" onClick={() => doExport("csv")}>CSV</Button>
        <Button variant="outline" size="sm" onClick={() => doExport("markdown")}>MD</Button>
      </div>
      <Button variant="outline" size="sm" className="w-full" onClick={createPlaylist} disabled={playlistBusy}>{playlistBusy ? "…" : "Crea playlist Spotify"}</Button>
      <Button variant="danger" size="sm" className="w-full" onClick={() => setConfirmDelete(true)}><Trash2 size={15} /> Elimina set</Button>
      <div className="space-y-2 border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2"><span className="text-muted">Tracce</span><span className="tnum text-fg">{n}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">Durata</span><span className="tnum text-fg">{fmtDuration(setlist.total_duration_seconds)}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">Origine</span><span className="text-fg">{setlist.generated_by === "ai" ? "AI" : "algoritmico"}</span></div>
      </div>
    </div>
  );

  return (
    <PageLayout title="Set" meta={`${n} TRACCE`} marginaliaTitle="Dettagli" marginalia={marginalia}>
      <Link href="/sets" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Set</Link>

      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              {setlist.name}
              <Badge tone={setlist.generated_by === "ai" ? "primary" : "neutral"}>
                {setlist.generated_by === "ai" ? <><Sparkles size={11} /> AI</> : "algoritmico"}
              </Badge>
              {setlist.owned_only && <Badge tone="success">solo posseduti</Badge>}
              <button
                onClick={() => { setRenameValue(setlist.name); setRenameOpen(true); }}
                title="Rinomina" className="text-faint transition-colors hover:text-fg"
              ><Pencil size={14} /></button>
            </span>
          }
          subtitle={`${n} tracce · ${fmtDuration(setlist.total_duration_seconds)}${busy ? " · aggiorno…" : ""}`}
        />

        <div className="space-y-4 p-5">
          {error && <Alert tone="danger">⚠ {error}</Alert>}
          {playlistUrl && <Alert tone="info">✓ Playlist creata: <a href={playlistUrl} target="_blank" rel="noreferrer" className="underline">{playlistUrl}</a></Alert>}

          {setlist.mixing_overview.length > 0 && (
            <details className="group border border-border">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3 py-2.5 text-xs font-semibold uppercase tracking-wide text-muted transition-colors hover:text-fg [&::-webkit-details-marker]:hidden">
                <span className="flex items-center gap-1.5"><SlidersHorizontal size={14} /> Come mixare il set</span>
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
                <span className="flex items-center gap-1.5"><Lightbulb size={14} /> Come migliorare il tuo set</span>
                <ChevronDown size={15} className="text-faint transition-transform duration-200 group-open:rotate-180" />
              </summary>
              <ul className="space-y-1 border-t border-border p-3 text-sm text-muted">
                {improvements.map((it, i) => <li key={i} className="flex gap-1.5"><span className="text-faint">·</span>{it}</li>)}
              </ul>
            </details>
          )}

          <ol className="space-y-1.5">
            {setlist.tracks.map((st) => (
              <li key={st.position} className="flex items-center gap-3 rounded-none border border-border bg-bg p-3">
                <span className="tnum w-5 text-right text-sm text-faint">{st.position}</span>
                <TrackCover track={st.track} className="h-10 w-10" iconSize={16} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    {st.role && <Badge tone="neutral">{st.role}</Badge>}
                    <Link href={`/tracks/${st.track.id}`} className="truncate font-medium hover:text-fg-strong">{trackLabel(st.track)}</Link>
                    <span className="tnum shrink-0 text-xs text-faint">{st.track.bpm?.toFixed(0) ?? "—"} BPM · {st.track.camelot_key ?? "?"} · {fmtDuration(st.track.duration_seconds)}</span>
                    {st.transition_class && (
                      <Badge tone="neutral">
                        <span title={st.transition_class_reason ?? undefined}>{st.transition_class_label ?? st.transition_class}</span>
                      </Badge>
                    )}
                  </div>
                  {st.mix_tip
                    ? <p className="mt-1 flex gap-1.5 text-xs text-muted"><span className="shrink-0 text-faint">↪</span>{st.mix_tip}</p>
                    : <p className="mt-1 text-xs text-faint">apertura del set</p>}
                </div>
                <div className="flex shrink-0 items-center gap-0.5">
                  <IconBtn title="Su" disabled={busy || st.position === 1} onClick={() => move(st.position, "up")}><ArrowUp size={15} /></IconBtn>
                  <IconBtn title="Giù" disabled={busy || st.position === n} onClick={() => move(st.position, "down")}><ArrowDown size={15} /></IconBtn>
                  <IconBtn title="Alternative" disabled={busy} onClick={() => loadAlternatives(st.position, "safer")}><Replace size={15} /></IconBtn>
                  <IconBtn title="Rimuovi" danger disabled={busy || n <= 1} onClick={() => remove(st.position)}><Trash2 size={15} /></IconBtn>
                </div>
              </li>
            ))}
          </ol>

          {exported && <pre className="max-h-72 overflow-auto rounded-none border border-border bg-bg p-3 text-xs text-muted">{exported}</pre>}
        </div>
      </Card>

      {/* Rinomina */}
      <Modal open={renameOpen} onClose={() => setRenameOpen(false)} title="Rinomina set"
        footer={<><Button variant="ghost" size="sm" onClick={() => setRenameOpen(false)}>Annulla</Button><Button size="sm" onClick={doRename}><Check size={15} /> Salva</Button></>}>
        <Input autoFocus value={renameValue} onChange={(e) => setRenameValue(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") doRename(); }} placeholder="Nome del set" />
      </Modal>

      {/* Conferma eliminazione */}
      <Modal open={confirmDelete} onClose={() => setConfirmDelete(false)} title="Eliminare il set?"
        footer={<><Button variant="ghost" size="sm" onClick={() => setConfirmDelete(false)}>Annulla</Button><Button variant="danger" size="sm" onClick={doDelete}><Trash2 size={15} /> Elimina</Button></>}>
        <p className="text-sm text-muted">«{setlist.name}» verrà eliminato definitivamente.</p>
      </Modal>

      {/* Alternative per traccia */}
      <Modal open={altPos != null} onClose={() => setAltPos(null)} size="lg"
        title={<span className="flex items-center gap-2"><Replace size={16} className="text-muted" /> Alternative {altTrack && <span className="truncate text-sm font-normal text-muted">· {trackLabel(altTrack.track)}</span>}</span>}>
        <div className="mb-3 flex flex-wrap gap-1.5">
          {MODES.map((m) => (
            <button key={m.key} onClick={() => altPos != null && loadAlternatives(altPos, m.key)}
              className={cn("rounded-none px-3 py-1 text-xs font-medium uppercase tracking-wider transition-colors",
                altMode === m.key ? "bg-fg-strong text-bg" : "bg-elevated text-muted hover:text-fg")}>
              {m.label}
            </button>
          ))}
        </div>

        {altLoading && <div className="flex items-center gap-2 py-6 text-sm text-muted"><Spinner /> Cerco alternative…</div>}
        {!altLoading && altItems && altItems.length === 0 && (
          <p className="py-6 text-center text-sm text-muted">Nessuna alternativa per questa modalità.</p>
        )}
        {!altLoading && altItems && altItems.length > 0 && (
          <ul className="space-y-1.5">
            {altItems.map((a) => (
              <li key={a.track.id} className="flex items-center gap-3 rounded-none border border-border bg-bg p-2.5">
                <TrackCover track={a.track} className="h-9 w-9" iconSize={15} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2">
                    <span className="truncate text-sm font-medium">{trackLabel(a.track)}</span>
                    <span className="tnum shrink-0 text-xs text-faint">{a.track.bpm?.toFixed(0) ?? "—"} · {a.track.camelot_key ?? "?"}</span>
                    <Badge tone="neutral">{a.risk_level}</Badge>
                  </div>
                  <p className="mt-0.5 truncate text-xs text-muted">{a.reason}
                    <span className="tnum text-faint"> · prev {a.score_prev ?? "—"}{a.score_next != null && ` · next ${a.score_next}`}</span>
                  </p>
                </div>
                <Button size="sm" variant="outline" onClick={() => substitute(a)}><Check size={14} /> Usa</Button>
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
