"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useState } from "react";
import {
  ArrowLeft, Sparkles, Download, Music4, AlertTriangle, Lightbulb, Compass,
  ArrowUp, ArrowDown, Trash2, Replace, Pencil, Check,
} from "lucide-react";
import {
  apiGet, apiPost, apiPatch, apiDelete, exportSet, fmtDuration, trackLabel,
  type Setlist, type Alternative, type AlternativeMode, type AlternativesResponse,
} from "@/lib/api";
import { Card, CardHeader, Button, Input, Badge, Alert, Modal, Spinner } from "@/components/ui";
import { cn } from "@/lib/cn";

const RISK_TONE = { low: "success", medium: "warning", high: "danger" } as const;
const MODES: { key: AlternativeMode; label: string }[] = [
  { key: "safer", label: "Più sicura" },
  { key: "softer", label: "Più morbida" },
  { key: "harder", label: "Più dura" },
  { key: "same_artist", label: "Stesso artista" },
  { key: "surprising", label: "Sorprendente" },
];

function riskTone(r: string | null) {
  return RISK_TONE[r as keyof typeof RISK_TONE] ?? "neutral";
}

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
    <div>
      <Link href="/sets" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Set</Link>
      <Alert tone="danger">⚠ {error}</Alert>
    </div>
  );
  if (!setlist) return <p className="text-muted">Caricamento…</p>;

  const v = setlist.validation ?? {};
  const n = setlist.tracks.length;
  const lists: Array<[string, string[] | undefined, "warning" | "info" | "primary", React.ReactNode]> = [
    ["Warning di validazione", v.warnings, "warning", <AlertTriangle key="w" size={14} />],
    ["Punti critici", v.critical_points, "warning", <AlertTriangle key="c" size={14} />],
    ["Direzioni alternative", v.alternative_directions, "info", <Compass key="a" size={14} />],
    ["Cosa manca in libreria", v.missing_library_suggestions, "primary", <Lightbulb key="m" size={14} />],
  ];
  const shown = lists.filter(([, items]) => items && items.length > 0);
  const altTrack = altPos != null ? setlist.tracks.find((st) => st.position === altPos) : null;

  return (
    <div>
      <Link href="/sets" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Set</Link>

      <Card>
        <CardHeader
          title={
            <span className="flex items-center gap-2">
              {setlist.name}
              <Badge tone={setlist.generated_by === "ai" ? "primary" : "neutral"}>
                {setlist.generated_by === "ai" ? <><Sparkles size={11} /> AI</> : "algoritmico"}
              </Badge>
              <button
                onClick={() => { setRenameValue(setlist.name); setRenameOpen(true); }}
                title="Rinomina" className="text-faint transition-colors hover:text-fg"
              ><Pencil size={14} /></button>
            </span>
          }
          subtitle={`${n} tracce · ${fmtDuration(setlist.total_duration_seconds)}${busy ? " · aggiorno…" : ""}`}
          action={
            <div className="flex shrink-0 items-center gap-2">
              <Button variant="outline" size="sm" onClick={() => doExport("text")}><Download size={14} /> Testo</Button>
              <Button variant="outline" size="sm" onClick={() => doExport("csv")}>CSV</Button>
              <Button variant="outline" size="sm" onClick={() => doExport("markdown")}>MD</Button>
              <Button variant="outline" size="sm" onClick={createPlaylist} disabled={playlistBusy}>{playlistBusy ? "…" : "Playlist Spotify"}</Button>
              <button onClick={() => setConfirmDelete(true)} title="Elimina set"
                className="grid h-8 w-8 place-items-center rounded-md text-faint transition-colors hover:bg-danger/15 hover:text-danger"><Trash2 size={15} /></button>
            </div>
          }
        />

        <div className="space-y-4 p-5">
          {error && <Alert tone="danger">⚠ {error}</Alert>}
          {playlistUrl && <Alert tone="success">✓ Playlist creata: <a href={playlistUrl} target="_blank" rel="noreferrer" className="underline">{playlistUrl}</a></Alert>}
          {setlist.global_explanation && <p className="text-sm leading-relaxed text-muted">{setlist.global_explanation}</p>}

          {shown.length > 0 && (
            <div className="grid gap-3 sm:grid-cols-2">
              {shown.map(([title, items, tone, icon]) => (
                <div key={title} className="rounded-lg border border-border bg-bg p-3">
                  <div className={`mb-1.5 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-${tone}`}>{icon} {title}</div>
                  <ul className="space-y-1 text-sm text-muted">
                    {items!.map((it, i) => <li key={i} className="flex gap-1.5"><span className="text-faint">·</span>{it}</li>)}
                  </ul>
                </div>
              ))}
            </div>
          )}

          <ol className="space-y-1.5">
            {setlist.tracks.map((st) => (
              <li key={st.position} className="flex items-center gap-3 rounded-lg border border-border bg-bg p-3">
                <span className="tnum w-5 text-right text-sm text-faint">{st.position}</span>
                {st.track.album_art_url
                  ? <img src={st.track.album_art_url} alt="" className="h-10 w-10 shrink-0 rounded object-cover" />
                  : <span className="grid h-10 w-10 shrink-0 place-items-center rounded bg-elevated text-faint"><Music4 size={16} /></span>}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    {st.role && <Badge tone="neutral">{st.role}</Badge>}
                    <Link href={`/tracks/${st.track.id}`} className="truncate font-medium hover:text-primary">{trackLabel(st.track)}</Link>
                    <span className="tnum shrink-0 text-xs text-faint">{st.track.bpm?.toFixed(0) ?? "—"} BPM · {st.track.camelot_key ?? "?"} · {fmtDuration(st.track.duration_seconds)}</span>
                    {st.risk_level && (
                      <Badge tone={riskTone(st.risk_level)}>
                        {st.risk_level}{st.transition_score != null && ` · ${st.transition_score.toFixed(0)}`}
                      </Badge>
                    )}
                  </div>
                  {st.ai_reason && <p className="mt-1 text-xs text-primary/85">🎧 {st.ai_reason}</p>}
                  {st.transition_note && <p className="mt-0.5 text-xs text-muted">↪ {st.transition_note}</p>}
                  {st.transition_reason && <p className="mt-0.5 text-xs text-faint">{st.transition_reason}</p>}
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

          {exported && <pre className="max-h-72 overflow-auto rounded-lg border border-border bg-bg p-3 text-xs text-muted">{exported}</pre>}
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
        title={<span className="flex items-center gap-2"><Replace size={16} className="text-primary" /> Alternative {altTrack && <span className="truncate text-sm font-normal text-muted">· {trackLabel(altTrack.track)}</span>}</span>}>
        <div className="mb-3 flex flex-wrap gap-1.5">
          {MODES.map((m) => (
            <button key={m.key} onClick={() => altPos != null && loadAlternatives(altPos, m.key)}
              className={cn("rounded-full px-3 py-1 text-xs font-medium transition-colors",
                altMode === m.key ? "bg-primary text-primary-fg" : "bg-elevated text-muted hover:text-fg")}>
              {m.label}
            </button>
          ))}
        </div>

        {altLoading && <div className="flex items-center gap-2 py-6 text-sm text-muted"><Spinner /> Cerco alternative…</div>}
        {!altLoading && altItems && altItems.length === 0 && (
          <p className="py-6 text-center text-sm text-faint">Nessuna alternativa per questa modalità.</p>
        )}
        {!altLoading && altItems && altItems.length > 0 && (
          <ul className="space-y-1.5">
            {altItems.map((a) => (
              <li key={a.track.id} className="flex items-center gap-3 rounded-lg border border-border bg-bg p-2.5">
                {a.track.album_art_url
                  ? <img src={a.track.album_art_url} alt="" className="h-9 w-9 shrink-0 rounded object-cover" />
                  : <span className="grid h-9 w-9 shrink-0 place-items-center rounded bg-elevated text-faint"><Music4 size={15} /></span>}
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-x-2">
                    <span className="truncate text-sm font-medium">{trackLabel(a.track)}</span>
                    <span className="tnum shrink-0 text-xs text-faint">{a.track.bpm?.toFixed(0) ?? "—"} · {a.track.camelot_key ?? "?"}</span>
                    <Badge tone={riskTone(a.risk_level)}>{a.risk_level}</Badge>
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
    </div>
  );
}

function IconBtn({ title, onClick, disabled, danger, children }: {
  title: string; onClick: () => void; disabled?: boolean; danger?: boolean; children: React.ReactNode;
}) {
  return (
    <button title={title} onClick={onClick} disabled={disabled}
      className={cn(
        "grid h-8 w-8 place-items-center rounded-md text-faint transition-colors hover:bg-elevated hover:text-fg disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-faint",
        danger && "hover:bg-danger/15 hover:text-danger",
      )}>
      {children}
    </button>
  );
}
