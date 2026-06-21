"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Radar, Music4, Eye, Trash2, AudioLines } from "lucide-react";
import {
  shazamStatus, identifyMix, shazamIdentifyStatus, listDjSets, deleteDjSet, fmtDate,
  type DjSet, type ShazamIdentifyState,
} from "@/lib/api";
import { Card, Badge, Alert, Button, EmptyState, Spinner, Progress, Input } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

const STATUS: Record<DjSet["status"], { tone: "success" | "info" | "danger" | "neutral"; label: string }> = {
  done: { tone: "success", label: "identificato" },
  identifying: { tone: "info", label: "in corso…" },
  error: { tone: "danger", label: "errore" },
  pending: { tone: "neutral", label: "in attesa" },
};

export default function ShazamPage() {
  const [available, setAvailable] = useState<boolean | null>(null);
  const [sets, setSets] = useState<DjSet[] | null>(null);
  const [url, setUrl] = useState("");
  const [job, setJob] = useState<ShazamIdentifyState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const reload = useCallback(() => {
    listDjSets().then(setSets).catch((e) => setError(err(e)));
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(async () => {
      try {
        const s = await shazamIdentifyStatus();
        setJob(s);
        if (s.status === "done") { stopPolling(); reload(); }
        else if (s.status === "idle") stopPolling();
        else if (s.status === "error") { stopPolling(); setError(s.error ?? "Identificazione fallita"); }
      } catch (e) { stopPolling(); setError(err(e)); }
    }, 1500);
  }, [reload, stopPolling]);

  useEffect(() => {
    shazamStatus().then((s) => setAvailable(s.available)).catch(() => setAvailable(false));
    reload();
    shazamIdentifyStatus()
      .then((s) => { setJob(s); if (s.status === "running") startPolling(); })
      .catch(() => {});
    return stopPolling;
  }, [reload, startPolling, stopPolling]);

  const identify = async () => {
    const u = url.trim();
    if (!u) return;
    setBusy(true);
    setError(null);
    try {
      const s = await identifyMix(u);
      setJob(s);
      setUrl("");
      if (s.cached || s.status === "done") reload();
      else startPolling();
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async (s: DjSet) => {
    if (!window.confirm(`Rimuovere il set "${s.title ?? s.source_url}" e le sue tracce identificate?`)) return;
    try { await deleteDjSet(s.id); reload(); } catch (e) { setError(err(e)); }
  };

  const running = job?.status === "running";
  const pct = job && job.total > 0 ? Math.round((job.processed / job.total) * 100) : null;

  const marginalia = (
    <p className="text-xs leading-relaxed text-muted">
      Sorgenti: SoundCloud, Mixcloud, YouTube. L&apos;audio viene scaricato solo temporaneamente per il fingerprinting, mai conservato.
    </p>
  );

  return (
    <PageLayout title="Shazam" meta={sets ? String(sets.length) : undefined} marginaliaTitle="Note" marginalia={marginalia}>
      <p className="mb-6 text-sm text-muted">Identifica le tracce di un set DJ da un URL (SoundCloud, Mixcloud, YouTube).</p>

      {available === false && (
        <div className="mb-4"><Alert tone="warning">
          Identificazione non disponibile: il backend richiede <code className="rounded-none bg-elevated px-1">ffmpeg</code>, <code className="rounded-none bg-elevated px-1">yt-dlp</code> e <code className="rounded-none bg-elevated px-1">shazamio</code>.
        </Alert></div>
      )}
      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <Card className="mb-6">
        <div className="flex flex-col gap-2 p-4 sm:flex-row">
          <Input
            placeholder="https://soundcloud.com/… · mixcloud.com/… · youtube.com/…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") identify(); }}
            disabled={available === false || running}
          />
          <Button onClick={identify} disabled={busy || running || available === false || !url.trim()} className="shrink-0">
            {busy || running ? <Spinner /> : <AudioLines size={16} />} Identifica
          </Button>
        </div>
        {running && (
          <div className="border-t border-border px-4 py-3">
            <div className="mb-1 flex items-center justify-between text-sm">
              <span className="flex items-center gap-2 font-medium"><Radar size={15} className="text-muted" /> {job?.phase ?? "Avvio…"}</span>
              {pct != null && <span className="tnum text-muted">{job?.processed}/{job?.total} ({pct}%)</span>}
            </div>
            <Progress value={pct} />
          </div>
        )}
      </Card>

      {sets && sets.length === 0 && (
        <EmptyState icon={<Radar size={28} />} title="Nessun set identificato">
          Incolla l&apos;URL di un mix e premi <strong>Identifica</strong> per estrarne la tracklist.
        </EmptyState>
      )}

      <div className="grid gap-3">
        {sets?.map((s) => {
          const st = STATUS[s.status];
          return (
            <Card key={s.id} className="p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                  {s.artwork_url
                    ? <img src={s.artwork_url} alt="" className="h-12 w-12 shrink-0 rounded-none object-cover" />
                    : <span className="grid h-12 w-12 shrink-0 place-items-center rounded-none bg-elevated text-faint"><Music4 size={18} /></span>}
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <Link href={`/shazam/${s.id}`} className="truncate font-medium hover:text-fg-strong">{s.title ?? s.source_url}</Link>
                      <Badge tone={st.tone}>{st.label}</Badge>
                      {s.platform && <Badge tone="neutral">{s.platform}</Badge>}
                    </div>
                    <div className="mt-0.5 truncate text-xs text-faint">
                      {s.dj_name ?? "—"} · {s.identified_count} tracce identificate · {fmtDate(s.created_at)}
                    </div>
                    {s.status === "error" && s.error && <div className="mt-1 truncate text-xs text-danger">⚠ {s.error}</div>}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  <Link href={`/shazam/${s.id}`}><Button size="sm" variant="outline"><Eye size={15} /> Apri</Button></Link>
                  <Button size="sm" variant="danger" onClick={() => doDelete(s)}><Trash2 size={15} /></Button>
                </div>
              </div>
            </Card>
          );
        })}
      </div>
    </PageLayout>
  );
}
