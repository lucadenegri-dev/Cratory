"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { ArrowLeft, Radar, Music4, ExternalLink, Clock, ListPlus, Check } from "lucide-react";
import {
  getDjSet, importDjSetAsPlaylist, discoverySaveForLater, fmtDuration, fmtDate,
  type DjSetDetail, type DjSetTrack, type Track,
} from "@/lib/api";
import { Card, CardHeader, Badge, Alert, Button, Spinner, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { ConfidenceBadge } from "@/components/confidence-badge";
import { PartialBadge, isPartial } from "@/components/partial-badge";
import { useT } from "@/lib/i18n";

// Polling mentre l'identificazione del set e' in corso: la Jobs bar globale non
// espone lo stato raw per-set, quindi il dettaglio fa polling diretto dell'endpoint
// finche' lo status non e' piu' "identifying".
const POLL_MS = 3000;

function TrackLibraryAction({ track, onSaved }: { track: DjSetTrack; onSaved: (track: Track) => void }) {
  const t = useT();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (track.library_status && track.library_track_id != null) {
    const owned = track.library_status === "owned";
    return (
      <Link href={`/tracks/${track.library_track_id}`} title={t.shazam.detail.viewInLibraryTitle} className="shrink-0">
        <Badge tone={owned ? "success" : "info"}>
          {owned ? t.shazam.detail.ownedBadge : t.shazam.detail.inLibraryBadge}
        </Badge>
      </Link>
    );
  }

  if (!track.artist || !track.title) return null;

  const saveAsLead = async () => {
    setSaving(true);
    setError(null);
    try {
      const res = await discoverySaveForLater({ artist: track.artist!, title: track.title! });
      setSaved(true);
      onSaved(res.track);
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Button
      size="sm"
      variant={saved ? "ghost" : "outline"}
      className="shrink-0"
      onClick={saveAsLead}
      disabled={saving || saved}
      title={error ?? undefined}
    >
      {saved ? <><Check size={14} /> {t.shazam.detail.savedAsLeadDone}</> : saving ? <Spinner /> : t.shazam.detail.saveAsLeadButton}
    </Button>
  );
}

export default function DjSetDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const t = useT();
  const { id } = use(params);
  const [set, setSet] = useState<DjSetDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [imported, setImported] = useState<{ id: number; created: number } | null>(null);

  useEffect(() => {
    getDjSet(Number(id)).then(setSet).catch((e) => setError(String(e.message ?? e)));
  }, [id]);

  // Il job di identificazione e' in background: mentre questo set e' "identifying"
  // rinfresca il dettaglio a intervalli, cosi' l'utente vede l'esito senza ricaricare.
  useEffect(() => {
    if (!set || set.status !== "identifying") return;
    const iv = setInterval(() => {
      getDjSet(Number(id)).then(setSet).catch(() => {});
    }, POLL_MS);
    return () => clearInterval(iv);
    // Solo id/status in dep: includere l'intero `set` riavvierebbe l'intervallo a ogni
    // poll (il fetch cambia l'oggetto). Lo status e' l'unico campo che deve far
    // ripartire/fermare il polling.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, set?.status]);

  // "Save as lead" crea la Track lato server ma il polling del set (POLL_MS) non
  // è garantito a rincorrere subito: aggiorna otticamente la riga corrispondente
  // cosi' il badge passa a in_library/owned senza aspettare il prossimo poll.
  const patchTrackSaved = (position: number, track: Track) => {
    setSet((cur) => cur && {
      ...cur,
      tracks: cur.tracks.map((trk) => trk.position === position
        ? { ...trk, library_track_id: track.id, library_status: track.has_local_file ? "owned" : "in_library" }
        : trk),
    });
  };

  const doImport = async () => {
    setImporting(true);
    setError(null);
    try {
      const r = await importDjSetAsPlaylist(Number(id));
      setImported({ id: r.playlist_id, created: r.created });
    } catch (e) {
      setError(String((e as Error).message ?? e));
    } finally {
      setImporting(false);
    }
  };

  if (error) return (
    <PageLayout title={t.shazam.detail.pageTitle}>
      <Link href="/shazam" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Shazam</Link>
      <Alert tone="danger">⚠ {error}</Alert>
    </PageLayout>
  );
  if (!set) return <PageLayout title={t.shazam.detail.pageTitle}><Loading /></PageLayout>;

  const importedPlaylistId = imported?.id ?? set.imported_playlist_id;

  const marginalia = (
    <div className="space-y-2 text-xs">
      <div className="flex justify-between gap-2"><span className="text-muted">{t.shazam.detail.djLabel}</span><span className="truncate text-fg">{set.dj_name ?? "—"}</span></div>
      <div className="flex justify-between gap-2"><span className="text-muted">{t.shazam.detail.tracksLabel}</span><span className="tnum text-fg">{set.identified_count}</span></div>
      {set.duration_seconds ? <div className="flex justify-between gap-2"><span className="text-muted">{t.shazam.detail.durationLabel}</span><span className="tnum text-fg">{fmtDuration(set.duration_seconds)}</span></div> : null}
      <a href={set.source_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex items-center gap-1 border-t border-border pt-3 text-fg underline-offset-4 hover:underline">
        <ExternalLink size={13} /> {t.shazam.detail.sourceLabel}
      </a>
      {set.tracks.length > 0 && (
        <div className="border-t border-border pt-3">
          {importedPlaylistId ? (
            <p className="text-[11px] text-muted">
              {t.shazam.detail.importedAsPlaylist(imported?.created)} ·{" "}
              <Link href={`/playlists/${importedPlaylistId}`} className="text-fg underline-offset-4 hover:underline">{t.shazam.detail.openLink}</Link>
            </p>
          ) : (
            <Button size="sm" variant="outline" className="w-full" onClick={doImport} disabled={importing}>
              {importing ? <Spinner /> : <ListPlus size={14} />} {t.shazam.detail.importAsPlaylistButton}
            </Button>
          )}
        </div>
      )}
    </div>
  );

  return (
    <PageLayout title={t.shazam.detail.pageTitle} meta={set.title ?? undefined} marginaliaTitle={t.shazam.detail.metaTitle} marginalia={marginalia}>
      <Link href="/shazam" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> Shazam</Link>

      <div className="mb-6 flex flex-wrap items-start gap-4">
        {set.artwork_url
          ? <img src={set.artwork_url} alt="" className="h-24 w-24 rounded-none object-cover" />
          : <span className="grid h-24 w-24 place-items-center rounded-none bg-surface-2 text-faint"><Radar size={30} /></span>}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{set.title ?? t.shazam.detail.untitledSet}</h1>
            {set.platform && <Badge tone="neutral">{set.platform}</Badge>}
            <PartialBadge set={set} />
          </div>
          <p className="mt-1 text-sm text-muted">
            {set.dj_name ?? "—"} · {t.shazam.identifiedTracksCount(set.identified_count)}
            {set.duration_seconds ? ` · ${fmtDuration(set.duration_seconds)}` : ""} · {fmtDate(set.created_at)}
          </p>
          {isPartial(set) && (
            <p className="mt-1 text-xs text-muted">{t.shazam.partialNote(fmtDuration(set.aborted_at_seconds!))}</p>
          )}
        </div>
      </div>

      <Card>
        <CardHeader title={t.shazam.detail.identifiedTracksHeading} subtitle={t.shazam.detail.identifiedTracksSubtitle} />
        {set.tracks.length === 0 ? (
          <p className="px-5 py-8 text-center text-sm text-muted">
            {t.shazam.detail.noTracksMessage(set.status === "error")}
          </p>
        ) : (
          <ol className="divide-y divide-border">
            {set.tracks.map((trk) => (
              <li key={trk.position} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <span className="tnum w-5 shrink-0 text-right text-faint">{trk.position}</span>
                <span className="tnum inline-flex w-14 shrink-0 items-center gap-1 text-xs text-faint">
                  <Clock size={12} /> {fmtDuration(trk.start_offset_seconds)}
                </span>
                <span className="grid h-8 w-8 shrink-0 place-items-center rounded-none bg-elevated text-faint"><Music4 size={14} /></span>
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-medium">{trk.artist ?? "?"}</span>
                  <span className="text-muted"> — {trk.title ?? "?"}</span>
                </span>
                {trk.isrc && <Badge tone="neutral" className="tnum shrink-0">{trk.isrc}</Badge>}
                <ConfidenceBadge confidence={trk.confidence} />
                <TrackLibraryAction track={trk} onSaved={(track) => patchTrackSaved(trk.position, track)} />
              </li>
            ))}
          </ol>
        )}
      </Card>
    </PageLayout>
  );
}
