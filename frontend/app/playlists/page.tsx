"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Download, ClipboardList, Music2, Eye, Trash2, Calendar, CloudDownload } from "lucide-react";
import {
  listImportedPlaylists,
  deletePlaylist,
  fmtDate,
  type Playlist,
} from "@/lib/api";
import { Card, Badge, Alert, Button, EmptyState, Spinner, Loading } from "@/components/ui";
import { ButtonLink } from "@/components/button-link";
import { ConfirmModal } from "@/components/confirm-modal";
import { PageLayout } from "@/components/page-layout";
import { PlaylistCover } from "@/components/playlist-cover";
import { useT } from "@/lib/i18n";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function PlaylistsPage() {
  const t = useT();
  const [imported, setImported] = useState<Playlist[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<Playlist | null>(null);

  const reload = useCallback(() => {
    listImportedPlaylists().then(setImported).catch((e) => setError(err(e)));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

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
      setError(t.playlists.deleteFailed(err(e)));
    } finally {
      setBusy(null);
    }
  };

  const totalTracks = imported?.reduce((sum, p) => sum + p.track_count, 0) ?? 0;

  const marginalia = (
    <div className="space-y-3">
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

      {imported && imported.length === 0 && (
        <EmptyState icon={<Music2 size={28} />} title={t.playlists.emptyTitle}>
          {t.playlists.emptyBody}
        </EmptyState>
      )}

      <div className="grid gap-3">
        {imported?.map((p, i) => (
          <Card key={p.id} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <span className="tnum text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
                <PlaylistCover artworkUrl={p.artwork_url} platform={p.platform} kind={p.kind} className="h-11 w-11 shrink-0" iconSize={18} placeholderClassName="bg-elevated" />
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Link href={`/playlists/${p.id}`} className="truncate font-medium hover:text-fg-strong">{p.name}</Link>
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
                <ButtonLink href={`/playlists/${p.id}`} size="sm" variant="outline">
                  <Eye size={15} /> {t.playlists.openButton}
                </ButtonLink>
                <Button size="sm" variant="danger" onClick={() => setConfirmDelete(p)} disabled={busy !== null}>
                  {busy === `del-${p.id}` ? <Spinner /> : <Trash2 size={15} />}
                </Button>
              </div>
            </div>
          </Card>
        ))}
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
