"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Radar, Music4, Eye, Trash2, AudioLines } from "lucide-react";
import {
  shazamStatus, identifyMix, shazamIdentifyStatus, listDjSets, deleteDjSet, fmtDate,
  type DjSet, type ShazamIdentifyState,
} from "@/lib/api";
import { Card, Badge, Alert, Button, EmptyState, Spinner, Input, Loading } from "@/components/ui";
import { ButtonLink } from "@/components/button-link";
import { ConfirmModal } from "@/components/confirm-modal";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { useT } from "@/lib/i18n";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ShazamPage() {
  const t = useT();
  const [available, setAvailable] = useState<boolean | null>(null);
  const [sets, setSets] = useState<DjSet[] | null>(null);
  const [url, setUrl] = useState("");
  const [job, setJob] = useState<ShazamIdentifyState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<DjSet | null>(null);
  const jobs = useJobs();
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const STATUS: Record<DjSet["status"], { tone: "success" | "info" | "danger" | "neutral"; label: string }> = {
    done: { tone: "success", label: t.shazam.statusDone },
    identifying: { tone: "info", label: t.shazam.statusIdentifying },
    error: { tone: "danger", label: t.shazam.statusError },
    pending: { tone: "neutral", label: t.shazam.statusPending },
  };

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
        else if (s.status === "error") { stopPolling(); setError(s.error ?? t.shazam.identifyFailed); }
      } catch (e) { stopPolling(); setError(err(e)); }
    }, 1500);
  }, [reload, stopPolling, t]);

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
      else { startPolling(); jobs.refresh(); }
    } catch (e) {
      setError(err(e));
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async (s: DjSet) => {
    try { await deleteDjSet(s.id); reload(); } catch (e) { setError(err(e)); }
  };

  const running = job?.status === "running";

  const marginalia = (
    <p className="text-xs leading-relaxed text-muted">
      {t.shazam.sourcesNote}
    </p>
  );

  return (
    <PageLayout title="Shazam" meta={sets ? String(sets.length) : undefined} marginaliaTitle={t.shazam.notesTitle} marginalia={marginalia}>
      <p className="mb-6 text-sm text-muted">{t.shazam.intro}</p>

      {available === false && (
        <div className="mb-4"><Alert tone="warning">
          {t.shazam.unavailablePrefix}<code className="rounded-none bg-elevated px-1">ffmpeg</code>, <code className="rounded-none bg-elevated px-1">yt-dlp</code>{t.shazam.unavailableAnd}<code className="rounded-none bg-elevated px-1">shazamio</code>.
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
            {busy || running ? <Spinner /> : <AudioLines size={16} />} {t.shazam.identifyButton}
          </Button>
        </div>
      </Card>

      {sets === null && !error && <Loading />}

      {sets && sets.length === 0 && (
        <EmptyState icon={<Radar size={28} />} title={t.shazam.emptyTitle}>
          {t.shazam.emptyBodyPrefix}<strong>{t.shazam.identifyButton}</strong>{t.shazam.emptyBodySuffix}
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
                      {s.dj_name ?? "—"} · {t.shazam.identifiedTracksCount(s.identified_count)} · {fmtDate(s.created_at)}
                    </div>
                    {s.status === "error" && s.error && <div className="mt-1 truncate text-xs text-danger">⚠ {s.error}</div>}
                  </div>
                </div>
                <div className="flex shrink-0 gap-1.5">
                  <ButtonLink href={`/shazam/${s.id}`} size="sm" variant="outline"><Eye size={15} /> {t.shazam.openButton}</ButtonLink>
                  <Button size="sm" variant="danger" onClick={() => setConfirmDelete(s)}><Trash2 size={15} /></Button>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      <ConfirmModal
        open={confirmDelete !== null}
        title={t.common.delete}
        message={confirmDelete ? t.shazam.deleteConfirm(confirmDelete.title ?? confirmDelete.source_url) : ""}
        tone="danger"
        confirmLabel={t.common.delete}
        onConfirm={() => {
          const s = confirmDelete;
          setConfirmDelete(null);
          if (s) doDelete(s);
        }}
        onClose={() => setConfirmDelete(null)}
      />
    </PageLayout>
  );
}
