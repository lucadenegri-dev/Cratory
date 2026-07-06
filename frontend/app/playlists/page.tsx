"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Download, ClipboardList, Music2, Eye, Trash2, Calendar, Music4 } from "lucide-react";
import {
  listImportedPlaylists,
  deletePlaylist,
  fmtDate,
  type Playlist,
} from "@/lib/api";
import { Card, Badge, Alert, Button, EmptyState, Spinner, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function PlaylistsPage() {
  const [imported, setImported] = useState<Playlist[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const reload = useCallback(() => {
    listImportedPlaylists().then(setImported).catch((e) => setError(err(e)));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const doDelete = async (p: Playlist) => {
    if (!window.confirm(`Rimuovere la playlist "${p.name}" e le sue ${p.track_count} tracce dalla libreria? L'operazione non si può annullare.`)) return;
    setError(null);
    setNotice(null);
    setBusy(`del-${p.id}`);
    try {
      await deletePlaylist(p.id);
      setNotice(`Playlist "${p.name}" rimossa.`);
      reload();
    } catch (e) {
      setError(`Rimozione fallita: ${err(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const totalTracks = imported?.reduce((sum, p) => sum + p.track_count, 0) ?? 0;

  const marginalia = (
    <div className="space-y-3">
      <Link href="/playlists/import-spotify" className="block"><Button size="sm" className="w-full"><Download size={15} /> Importa da Spotify</Button></Link>
      <Link href="/playlists/import-manual" className="block"><Button size="sm" variant="outline" className="w-full"><ClipboardList size={15} /> Inserisci manualmente</Button></Link>
      {imported && imported.length > 0 && (
        <div className="space-y-2 border-t border-border pt-4 text-xs">
          <div className="flex justify-between gap-2"><span className="text-muted">Playlist</span><span className="tnum text-fg">{imported.length}</span></div>
          <div className="flex justify-between gap-2"><span className="text-muted">Tracce totali</span><span className="tnum text-fg">{totalTracks}</span></div>
        </div>
      )}
    </div>
  );

  return (
    <PageLayout title="Playlist" meta={imported ? String(imported.length) : undefined} marginaliaTitle="Sorgente" marginalia={marginalia}>
      <p className="mb-6 text-sm text-muted">
        Le playlist importate sono liste di lead: candidati da procurare e pianificare.
        La libreria — ciò che possiedi — è il disco.
      </p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {imported === null && !error && <Loading />}
      {notice && <div className="mb-4"><Alert tone="info">{notice}</Alert></div>}

      {imported && imported.length === 0 && (
        <EmptyState icon={<Music2 size={28} />} title="Nessuna playlist importata">
          Usa “Importa da Spotify” o “Inserisci manualmente” per iniziare a costruire un set.
        </EmptyState>
      )}

      <div className="grid gap-3">
        {imported?.map((p, i) => (
          <Card key={p.id} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <span className="tnum text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
                {p.artwork_url
                  ? <img src={p.artwork_url} alt="" className="h-11 w-11 shrink-0 rounded-none object-cover" />
                  : <span className="grid h-11 w-11 shrink-0 place-items-center rounded-none bg-elevated text-faint"><Music4 size={18} /></span>}
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Link href={`/playlists/${p.id}`} className="truncate font-medium hover:text-fg-strong">{p.name}</Link>
                    <Badge tone="neutral">{p.platform}</Badge>
                    {p.kind === "liked" && <Badge tone="neutral">liked</Badge>}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-faint">
                    <span>{p.track_count} tracce</span>
                    <span>· {p.owner ?? "—"}</span>
                    <span className="inline-flex items-center gap-1">· <Calendar size={11} /> importata il {fmtDate(p.imported_at)}</span>
                  </div>
                </div>
              </div>
              <div className="flex shrink-0 gap-1.5">
                <Link href={`/playlists/${p.id}`}>
                  <Button size="sm" variant="outline"><Eye size={15} /> Apri</Button>
                </Link>
                <Button size="sm" variant="danger" onClick={() => doDelete(p)} disabled={busy !== null}>
                  {busy === `del-${p.id}` ? <Spinner /> : <Trash2 size={15} />}
                </Button>
              </div>
            </div>
          </Card>
        ))}
      </div>
    </PageLayout>
  );
}
