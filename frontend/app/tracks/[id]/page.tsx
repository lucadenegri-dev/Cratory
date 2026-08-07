"use client";

import Link from "next/link";
import { Suspense, use, useEffect, useState } from "react";
import { useBackLink } from "@/lib/back-link";
import { ArrowLeft, Check, Download, ExternalLink, Link2, ArrowRightLeft, Pencil } from "lucide-react";
import { apiGet, downloadTrackAuto, downloadTrackSoundcloud, fmtDuration, transitions, trackLabel, type TrackDetail, type TransitionCandidate } from "@/lib/api";
import { Card, CardHeader, Badge, Alert, Button, Loading, Spinner } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { TrackEditModal } from "@/components/track-edit-modal";
import { TrackCover } from "@/components/track-cover";
import { LinkLocalFileModal } from "@/components/link-local-file-modal";
import { TrackPlayButton } from "@/components/track-play-button";
import { AddToPlaylistMenu } from "@/components/add-to-playlist-menu";
import { RatingDiamond } from "@/components/rating-diamond";
import { useT } from "@/lib/i18n";

function TransitionList({ title, items, emptyLabel }: { title: string; items: TransitionCandidate[]; emptyLabel: string }) {
  return (
    <Card>
      <CardHeader title={title} />
      <ul className="divide-y divide-border">
        {items.map(({ track, score }) => (
          <li key={track.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
            <Badge tone="neutral" className="tnum w-9 justify-center">{score.score}</Badge>
            <Link href={`/tracks/${track.id}`} className="min-w-0 flex-1 truncate hover:text-fg-strong">{trackLabel(track)}</Link>
            <span className="tnum shrink-0 text-xs text-faint">{track.bpm?.toFixed(0)} · {track.camelot_key ?? "?"}</span>
          </li>
        ))}
        {items.length === 0 && <li className="px-4 py-6 text-center text-sm text-muted">{emptyLabel}</li>}
      </ul>
    </Card>
  );
}

function TrackPageInner({ params }: { params: Promise<{ id: string }> }) {
  const t = useT();
  const { id } = use(params);
  // Al dettaglio traccia si arriva da mezza app (libreria, playlist, etichette,
  // set, transizioni, wishlist, Shazam): il link indietro torna dove eri, filtri
  // compresi. Senza `from` (link diretto, refresh) ripiega sulla libreria.
  const back = useBackLink({ href: "/library", labelKey: "library" });
  const [track, setTrack] = useState<TrackDetail | null>(null);
  const [compatible, setCompatible] = useState<TransitionCandidate[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [linking, setLinking] = useState(false);
  const [dlState, setDlState] = useState<"idle" | "running" | "queued">("idle");
  const [dlError, setDlError] = useState<string | null>(null);
  const [scState, setScState] = useState<"idle" | "running" | "queued">("idle");
  const [scError, setScError] = useState<string | null>(null);

  useEffect(() => {
    apiGet<TrackDetail>(`/api/tracks/${id}`).then(setTrack).catch((e) => setError(String(e.message ?? e)));
    transitions(id, { limit: 8 }).then(setCompatible).catch(() => {});
  }, [id]);

  const refresh = () => {
    apiGet<TrackDetail>(`/api/tracks/${id}`).then(setTrack).catch(() => {});
  };

  if (error) return <PageLayout title={t.tracks.pageTitle}><Alert tone="danger">⚠ {error}</Alert></PageLayout>;
  if (!track) return <PageLayout title={t.tracks.pageTitle}><Loading /></PageLayout>;

  const searchSoulseek = async () => {
    setDlState("running");
    setDlError(null);
    try {
      await downloadTrackAuto(track.id);
      // Il job bar globale (jobs provider) aggancia il progresso da solo.
      setDlState("queued");
    } catch (e) {
      setDlError(String((e as { message?: string })?.message ?? e));
      setDlState("idle");
    }
  };

  const downloadSoundcloud = async () => {
    setScState("running");
    setScError(null);
    try {
      await downloadTrackSoundcloud(track.id);
      // Stesso job bar globale del download Soulseek: aggancia il progresso da solo.
      setScState("queued");
    } catch (e) {
      setScError(String((e as { message?: string })?.message ?? e));
      setScState("idle");
    }
  };

  const rows: Array<[string, React.ReactNode]> = [
    ["Album", track.album ?? "—"], [t.tracks.rowGenre, track.genre ?? "—"], [t.tracks.rowYear, track.year ?? "—"],
    ["BPM", track.bpm?.toFixed(2) ?? "—"], ["Key (Camelot)", track.camelot_key ?? "—"], [t.tracks.rowDuration, fmtDuration(track.duration_seconds)],
    [t.tracks.rowEnergy, track.energy ?? "—"], [t.tracks.rowLabel, track.label ?? "—"],
    [t.tracks.rowSource, track.source_type], ["ISRC", track.isrc ?? "—"], [t.tracks.rowStatus, track.status],
    ["Playlist", track.playlists.length ? track.playlists.map((p) => p.name).join(", ") : "—"],
  ];

  const marginalia = (
    <div className="space-y-4">
      <div className="flex flex-col gap-2">
        <RatingDiamond
          trackId={track.id}
          rating={track.rating}
          size={22}
          onSaved={(r) => setTrack((cur) => (cur ? { ...cur, rating: r } : cur))}
        />
        <Button size="sm" variant="outline" onClick={() => setEditing(true)}><Pencil size={14} /> {t.tracks.editValues}</Button>
        <AddToPlaylistMenu track={track} onChanged={refresh} />
      </div>
      <div className="space-y-2 border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2"><span className="text-muted">{t.tracks.rowSource}</span><span className="text-fg">{track.source_type}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">{t.tracks.rowStatus}</span><span className="text-fg">{track.status}</span></div>
        <div className="flex justify-between gap-2"><span className="text-muted">{t.tracks.rowLabel}</span><span className="truncate text-fg">{track.label ?? "—"}</span></div>
      </div>
    </div>
  );

  return (
    <PageLayout title={t.tracks.pageTitle} meta={track.artist ?? undefined} marginaliaTitle={t.tracks.detailsTitle} marginalia={marginalia}>
      <Link href={back.href} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg"><ArrowLeft size={15} /> {back.label}</Link>

      <div className="mb-6 flex items-center gap-4">
        <TrackCover track={track} className="h-20 w-20" iconSize={28} />
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{track.title ?? <span className="italic text-faint">{t.tracks.untitledHeading}</span>}</h1>
          <p className="text-muted">{track.artist ?? t.tracks.unknownArtist}</p>
          {track.spotify_url && (
            <a href={track.spotify_url} target="_blank" rel="noreferrer" className="mt-2 inline-flex"><Button size="sm" variant="outline"><ExternalLink size={14} /> Spotify</Button></a>
          )}
          {track.platform === "soundcloud" && track.url && (
            <a href={track.url} target="_blank" rel="noreferrer" className="mt-2 inline-flex"><Button size="sm" variant="outline"><ExternalLink size={14} /> SoundCloud</Button></a>
          )}
        </div>
      </div>

      <Card>
        <CardHeader title={t.tracks.metadataTitle} />
        <table className="w-full text-sm">
          <tbody>
            {rows.map(([k, v]) => (
              <tr key={k} className="border-b border-border/50 last:border-0">
                <td className="px-4 py-2 text-muted">{k}</td>
                <td className="px-4 py-2 tnum text-right">{v}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <div className="mt-6">
        <Card>
          <CardHeader
            title={t.tracks.diskCardTitle}
            action={
              <div className="flex items-center gap-2">
                {!track.has_local_file && (
                  <Button size="sm" variant={dlState === "queued" ? "ghost" : "outline"} onClick={searchSoulseek} disabled={dlState !== "idle"}>
                    {dlState === "queued" ? <><Check size={14} /> {t.tracks.soulseekQueued}</>
                      : dlState === "running" ? <Spinner />
                      : <><Download size={14} /> {t.tracks.searchSoulseek}</>}
                  </Button>
                )}
                {!track.has_local_file && track.platform === "soundcloud" && track.url && (
                  <Button size="sm" variant={scState === "queued" ? "ghost" : "outline"} onClick={downloadSoundcloud} disabled={scState !== "idle"}>
                    {scState === "queued" ? <><Check size={14} /> {t.tracks.soundcloudQueued}</>
                      : scState === "running" ? <Spinner />
                      : <><Download size={14} /> {t.tracks.downloadSoundcloud}</>}
                  </Button>
                )}
                <Button size="sm" variant="outline" onClick={() => setLinking(true)}>
                  <Link2 size={14} /> {track.has_local_file ? t.tracks.replaceFile : t.tracks.linkFile}
                </Button>
              </div>
            }
          />
          {dlError && <p className="border-b border-border/50 px-4 py-2 text-xs text-danger">⚠ {dlError}</p>}
          {scError && <p className="border-b border-border/50 px-4 py-2 text-xs text-danger">⚠ {scError}</p>}
          <table className="w-full text-sm">
            <tbody>
              <tr className="border-b border-border/50 last:border-0">
                <td className="px-4 py-2 text-muted">{t.tracks.rowStatus}</td>
                <td className="px-4 py-2 text-right">
                  <div className="inline-flex items-center gap-2">
                    <TrackPlayButton track={track} />
                    {track.has_local_file ? <Badge tone="success">{t.tracks.badgeOwned}</Badge>
                      : track.archived ? <Badge tone="neutral">{t.tracks.badgeArchived}</Badge>
                      : <Badge tone="neutral">{t.tracks.badgeNoFile}</Badge>}
                  </div>
                </td>
              </tr>
              {track.local_path && (
                <tr className="border-b border-border/50 last:border-0">
                  <td className="px-4 py-2 text-muted">File</td>
                  <td className="break-all px-4 py-2 text-right font-mono text-xs">{track.local_path}</td>
                </tr>
              )}
              {track.local_format && (
                <tr className="border-b border-border/50 last:border-0">
                  <td className="px-4 py-2 text-muted">{t.tracks.rowFormat}</td>
                  <td className="px-4 py-2 tnum text-right">
                    {track.local_format.toUpperCase()}{track.local_bitrate ? ` · ${track.local_bitrate} kbps` : ""}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </Card>
      </div>

      <h2 className="mb-3 mt-8 flex items-center gap-2 text-lg font-semibold tracking-tight"><ArrowRightLeft size={18} className="text-muted" /> {t.tracks.transitionsHeading}</h2>
      <TransitionList title={t.tracks.compatibleHeading} items={compatible} emptyLabel={t.tracks.noTransitions} />

      <TrackEditModal
        track={track}
        open={editing}
        onClose={() => setEditing(false)}
        onSaved={(saved) => setTrack(saved)}
      />

      <LinkLocalFileModal
        target={linking ? { id: track.id, artist: track.artist, title: track.title } : null}
        onClose={() => setLinking(false)}
        onLinked={(t) => setTrack(t)}
      />
    </PageLayout>
  );
}

export default function TrackPage(props: { params: Promise<{ id: string }> }) {
  return <Suspense><TrackPageInner {...props} /></Suspense>;
}
