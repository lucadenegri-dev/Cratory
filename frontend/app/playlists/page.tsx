"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { Download, ClipboardList, Music2, Eye, Trash2, Calendar, CloudDownload, RefreshCw } from "lucide-react";
import {
  listImportedPlaylists,
  deletePlaylist,
  syncAllPlaylists,
  errText,
  fmtDate,
  type Playlist,
  type PlaylistsSyncAllReport,
} from "@/lib/api";
import { Card, Badge, Alert, Button, EmptyState, Spinner, Loading } from "@/components/ui";
import { ButtonLink } from "@/components/button-link";
import { ConfirmModal } from "@/components/confirm-modal";
import { PageLayout } from "@/components/page-layout";
import { PlaylistCover } from "@/components/playlist-cover";
import { useJobs } from "@/components/jobs-provider";
import { useT } from "@/lib/i18n";
import { withFrom } from "@/lib/back-link";

export default function PlaylistsPage() {
  const t = useT();
  const jobs = useJobs();
  const from = usePathname();
  const [imported, setImported] = useState<Playlist[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Playlist | null>(null);
  const [startingSyncAll, setStartingSyncAll] = useState(false);
  const [syncAllReport, setSyncAllReport] = useState<PlaylistsSyncAllReport | null>(null);
  const [syncAllError, setSyncAllError] = useState<string | null>(null);
  // Slot singolo lato backend: qualsiasi import/sync in corso blocca il bottone.
  const jobRunning = jobs.streamingImport?.status === "running";

  const reload = useCallback(() => {
    listImportedPlaylists().then(setImported).catch((e) => setError(errText(e)));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  // Import/sync streaming girano in background (barra job globale): quando
  // finiscono (running -> done) l'elenco qui e' stantio, ricarica in automatico
  // (stesso pattern di /analysis con jobs.analysis).
  const prevStreamingImportStatus = useRef<string | null>(null);
  useEffect(() => {
    const status = jobs.streamingImport?.status ?? null;
    // Lo slot job e' condiviso da tutti gli import/sync streaming (playlist
    // singola, liked, SoundCloud, sync singolo): solo il sync di massa deve
    // alimentare questo riepilogo, altrimenti il fallimento di un import
    // qualsiasi comparirebbe sotto "Sincronizza tutte" come suo esito.
    const isSyncAll = jobs.streamingImport?.kind === "playlists_sync_all";
    if (prevStreamingImportStatus.current === "running") {
      // Entrambi i rami sotto risincronizzano lo stato locale da un sistema
      // esterno (il poller job), non generano un loop: la soppressione vale
      // per entrambe le setState anche se il linter la ancora solo alla prima.
      if (status === "done") {
        if (isSyncAll) {
          // Il riepilogo resta qui: la barra job svanisce dopo pochi secondi
          // e porterebbe via con sé l'elenco delle fallite.
          // eslint-disable-next-line react-hooks/set-state-in-effect
          setSyncAllReport(jobs.streamingImport?.sync_all ?? null);
        }
        reload(); // la lista e' stantia dopo qualsiasi import/sync, non solo il sync di massa
      } else if (status === "error" && isSyncAll) {
        setSyncAllError(jobs.streamingImport?.error ?? null);
      }
    }
    prevStreamingImportStatus.current = status;
  }, [
    jobs.streamingImport?.status,
    jobs.streamingImport?.kind,
    jobs.streamingImport?.sync_all,
    jobs.streamingImport?.error,
    reload,
  ]);

  const doSyncAll = async () => {
    setError(null);
    setNotice(null);
    setSyncAllReport(null);
    setSyncAllError(null);
    setStartingSyncAll(true);
    try {
      await syncAllPlaylists();
      // Il sync gira in background (barra job globale): senza questo refresh
      // jobRunning resta false fino al prossimo poll (POLL_MS), lasciando il
      // bottone cliccabile per un paio di secondi (stesso pattern di doSync
      // in playlists/detail/page.tsx).
      jobs.refresh();
      setNotice(t.playlists.syncAllStarted);
    } catch (e) {
      setError(errText(e));
    } finally {
      setStartingSyncAll(false);
    }
  };

  const doDelete = async (p: Playlist) => {
    setError(null);
    setNotice(null);
    setBusy(`del-${p.id}`);
    try {
      const { deleted_tracks } = await deletePlaylist(p.id);
      setNotice(
        deleted_tracks > 0
          ? t.playlists.deletedWithOrphans(p.name, deleted_tracks)
          : t.playlists.deleted(p.name),
      );
      reload();
    } catch (e) {
      setError(t.playlists.deleteFailed(errText(e)));
    } finally {
      setBusy(null);
    }
  };

  const totalTracks = imported?.reduce((sum, p) => sum + p.track_count, 0) ?? 0;

  // Playlist di sistema fissate in alto in una sezione dedicata, in ordine
  // fisso: Discovery, Top, SoundCloud Likes, Spotify Likes.
  const specialRank = (p: Playlist) =>
    p.kind === "discovery" ? 0 : p.kind === "rating_top" ? 1 : p.platform === "soundcloud" ? 2 : 3;
  const isSpecial = (p: Playlist) => p.kind === "discovery" || p.kind === "rating_top" || p.kind === "liked";
  const specials = (imported ?? []).filter(isSpecial).sort((a, b) => specialRank(a) - specialRank(b));
  const regular = (imported ?? []).filter((p) => !isSpecial(p));

  // Card condivisa tra le due sezioni: le speciali non hanno numero d'ordine,
  // la numerazione progressiva appartiene solo all'archivio delle importate.
  const renderCard = (p: Playlist, ordinal?: string) => (
    <Card key={p.id} className="p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {ordinal && <span className="tnum text-xs text-faint">{ordinal}</span>}
          <PlaylistCover artworkUrl={p.artwork_url} platform={p.platform} kind={p.kind} className="h-11 w-11 shrink-0" iconSize={18} placeholderClassName="bg-elevated" />
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <Link href={withFrom(`/playlists/detail?id=${p.id}`, from)} className="truncate font-medium hover:text-fg-strong">{p.name}</Link>
              <Badge tone="neutral">{p.platform}</Badge>
              {p.kind === "liked" && <Badge tone="neutral">liked</Badge>}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-faint">
              <span>{t.playlists.trackCount(p.track_count)}</span>
              <span>· {p.owner ?? "—"}</span>
              <span className="inline-flex items-center gap-1">· <Calendar size={11} /> {t.playlists.importedOn(fmtDate(p.imported_at))}</span>
            </div>
          </div>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <ButtonLink href={withFrom(`/playlists/detail?id=${p.id}`, from)} size="sm" variant="outline">
            <Eye size={15} /> {t.playlists.openButton}
          </ButtonLink>
          <Button size="sm" variant="danger" onClick={() => setConfirmDelete(p)} disabled={busy !== null}>
            {busy === `del-${p.id}` ? <Spinner /> : <Trash2 size={15} />}
          </Button>
        </div>
      </div>
    </Card>
  );

  const marginalia = (
    <div className="space-y-3">
      <Button size="sm" variant="outline" className="w-full" onClick={doSyncAll} disabled={startingSyncAll || jobRunning}>
        {startingSyncAll ? <Spinner /> : <RefreshCw size={15} />} {t.playlists.syncAllButton}
      </Button>
      <ButtonLink href="/playlists/import-spotify" size="sm" block><Download size={15} /> {t.playlists.importSpotifyButton}</ButtonLink>
      <ButtonLink href="/playlists/import-soundcloud" size="sm" block><CloudDownload size={15} /> {t.playlists.importSoundcloudButton}</ButtonLink>
      <ButtonLink href="/playlists/import-manual" size="sm" variant="outline" block><ClipboardList size={15} /> {t.playlists.importManualButton}</ButtonLink>
      {imported && imported.length > 0 && (
        <div className="space-y-2 border-t border-border pt-4 text-xs">
          <div className="flex justify-between gap-2"><span className="text-muted">{t.playlists.statsPlaylists}</span><span className="tnum text-fg">{imported.length}</span></div>
          <div className="flex justify-between gap-2"><span className="text-muted">{t.playlists.statsTracksTotal}</span><span className="tnum text-fg">{totalTracks}</span></div>
        </div>
      )}
    </div>
  );

  return (
    <PageLayout title={t.playlists.pageTitle} meta={imported ? String(imported.length) : undefined} marginaliaTitle={t.playlists.marginaliaSource} marginalia={marginalia}>
      <p className="mb-6 text-sm text-muted">
        {t.playlists.intro}
      </p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {imported === null && !error && <Loading />}
      {notice && <div className="mb-4"><Alert tone="info">{notice}</Alert></div>}
      {syncAllError && <div className="mb-4"><Alert tone="danger">⚠ {syncAllError}</Alert></div>}
      {syncAllReport && (
        <div className="mb-4">
          <Alert tone={syncAllReport.failed > 0 ? "warning" : "info"}>
            <p>{t.playlists.syncAllSummary(syncAllReport.synced, syncAllReport.created, syncAllReport.removed)}</p>
            {syncAllReport.failures.length > 0 && (
              <>
                <p className="mt-2 font-medium">{t.playlists.syncAllFailuresHeading(syncAllReport.failures.length)}</p>
                <ul className="mt-1 list-disc space-y-0.5 pl-5 text-xs">
                  {syncAllReport.failures.map((f) => (
                    <li key={f.playlist_id}><span className="font-medium">{f.name}</span> — {f.error}</li>
                  ))}
                </ul>
              </>
            )}
          </Alert>
        </div>
      )}

      {imported && imported.length === 0 && (
        <EmptyState icon={<Music2 size={28} />} title={t.playlists.emptyTitle}>
          {t.playlists.emptyBody}
        </EmptyState>
      )}

      {specials.length > 0 && (
        <div className="mb-8">
          <h2 className="mb-3 text-xs uppercase tracking-wide text-faint">{t.playlists.specialsHeading}</h2>
          <div className="grid gap-3">
            {specials.map((p) => renderCard(p))}
          </div>
        </div>
      )}
      {specials.length > 0 && regular.length > 0 && (
        <h2 className="mb-3 text-xs uppercase tracking-wide text-faint">{t.playlists.importedHeading}</h2>
      )}
      <div className="grid gap-3">
        {regular.map((p, i) => renderCard(p, String(i + 1).padStart(2, "0")))}
      </div>

      <ConfirmModal
        open={confirmDelete !== null}
        title={t.common.delete}
        message={confirmDelete ? t.playlists.deleteConfirm(confirmDelete.name) : ""}
        tone="danger"
        confirmLabel={t.common.delete}
        onConfirm={() => {
          const p = confirmDelete;
          setConfirmDelete(null);
          if (p) doDelete(p);
        }}
        onClose={() => setConfirmDelete(null)}
      />
    </PageLayout>
  );
}
