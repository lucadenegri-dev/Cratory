"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Download, ClipboardList, Sparkles, AlertTriangle, Info, Music2, Eye, Trash2, Calendar,
} from "lucide-react";
import {
  listImportedPlaylists,
  playlistGaps,
  deletePlaylist,
  enrichPlaylist,
  enrichmentJobStatus,
  featureEnrichSummary,
  fmtDate,
  type GapAnalysis,
  type Playlist,
  type FeatureEnrichJob,
} from "@/lib/api";
import { Card, Badge, Alert, Button, EmptyState, Spinner, Progress } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function PlaylistsPage() {
  const [imported, setImported] = useState<Playlist[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [gaps, setGaps] = useState<Record<number, GapAnalysis>>({});
  const [job, setJob] = useState<FeatureEnrichJob | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const reload = useCallback(() => {
    listImportedPlaylists().then(setImported).catch((e) => setError(err(e)));
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const s = await enrichmentJobStatus();
        setJob(s);
        if (s.status === "done") { stopPolling(); reload(); }
        else if (s.status === "idle") stopPolling();
        else if (s.status === "error") { stopPolling(); setError(s.error ?? "Arricchimento fallito"); }
      } catch (e) { stopPolling(); setError(err(e)); }
    }, 1000);
  }, [reload, stopPolling]);

  useEffect(() => {
    reload();
    // Se un arricchimento è già in corso (es. avviato dall'auto-enrichment dopo
    // l'import), riaggancia il polling per mostrarne l'avanzamento.
    enrichmentJobStatus()
      .then((s) => { setJob(s); if (s.status === "running") startPolling(); })
      .catch(() => {});
    return stopPolling;
  }, [reload, startPolling, stopPolling]);

  const doReEnrich = async (p: Playlist) => {
    setError(null);
    setNotice(null);
    setBusy(`enrich-${p.id}`);
    try {
      setJob(await enrichPlaylist(p.id));
      startPolling();
    } catch (e) {
      setError(`Arricchimento di "${p.name}" fallito: ${err(e)}`);
    } finally {
      setBusy(null);
    }
  };

  const loadGaps = async (id: number) => {
    setBusy(`gaps-${id}`);
    try {
      const result = await playlistGaps(id);
      setGaps((g) => ({ ...g, [id]: result }));
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(null);
    }
  };

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

  const running = job?.status === "running";
  const pct = job && job.total > 0 ? Math.round((job.processed / job.total) * 100) : null;
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
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}
      {notice && <div className="mb-4"><Alert tone="info">{notice}</Alert></div>}

      {/* Avanzamento arricchimento (auto dopo import o ri-arricchimento manuale) */}
      {running && job && (
        <Card className="mb-4">
          <div className="p-4">
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 font-medium"><Sparkles size={15} className="text-muted" /> Arricchimento in corso…</span>
              <span className="tnum text-muted">{job.processed}/{job.total || "?"}{pct != null ? ` (${pct}%)` : ""}</span>
            </div>
            <Progress value={pct} />
          </div>
        </Card>
      )}
      {job?.status === "done" && job.result && (
        <div className="mb-4"><Alert tone="info">✓ Arricchimento completato: {featureEnrichSummary(job.result)}.</Alert></div>
      )}

      {imported && imported.length === 0 && (
        <EmptyState icon={<Music2 size={28} />} title="Nessuna playlist importata">
          Usa “Importa da Spotify” o “Inserisci manualmente” per iniziare a costruire un set.
        </EmptyState>
      )}

      <div className="grid gap-3">
        {imported?.map((p, i) => (
          <Card key={p.id} className="p-4">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="tnum text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
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
              <div className="flex shrink-0 gap-1.5">
                <Link href={`/playlists/${p.id}`}>
                  <Button size="sm" variant="outline"><Eye size={15} /> Apri</Button>
                </Link>
                <Button size="sm" variant="ghost" onClick={() => doReEnrich(p)} disabled={busy !== null || running}>
                  {busy === `enrich-${p.id}` ? <Spinner /> : <Sparkles size={15} />} Arricchisci
                </Button>
                <Button size="sm" variant="ghost" onClick={() => loadGaps(p.id)} disabled={busy !== null}>
                  {busy === `gaps-${p.id}` ? <Spinner /> : <AlertTriangle size={15} />} Buchi
                </Button>
                <Button size="sm" variant="danger" onClick={() => doDelete(p)} disabled={busy !== null}>
                  {busy === `del-${p.id}` ? <Spinner /> : <Trash2 size={15} />}
                </Button>
              </div>
            </div>

            {gaps[p.id] && (
              <div className="mt-3 grid gap-2 border-t border-border pt-3">
                {gaps[p.id].gaps.length === 0 && (
                  <p className="text-sm text-fg">Nessun problema rilevante: la playlist è abbastanza bilanciata.</p>
                )}
                {gaps[p.id].gaps.map((g) => (
                  <div key={g.gap_type} className="flex gap-2 text-sm">
                    {g.severity === "warning"
                      ? <AlertTriangle size={15} className="mt-0.5 shrink-0 text-muted" />
                      : <Info size={15} className="mt-0.5 shrink-0 text-muted" />}
                    <div>
                      <span className="text-fg">{g.description}</span>{" "}
                      <span className="text-muted">{g.suggestion}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </PageLayout>
  );
}
