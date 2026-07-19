"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Radar, Music4, Eye, Trash2, AudioLines } from "lucide-react";
import {
  shazamStatus, identifyMix, listDjSets, deleteDjSet, errText, fmtDate, fmtDuration,
  type DjSet,
} from "@/lib/api";
import { Card, Badge, Alert, Button, EmptyState, Spinner, Input, Loading } from "@/components/ui";
import { ButtonLink } from "@/components/button-link";
import { ConfirmModal } from "@/components/confirm-modal";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { useT } from "@/lib/i18n";

export default function ShazamPage() {
  const t = useT();
  const [available, setAvailable] = useState<boolean | null>(null);
  const [sets, setSets] = useState<DjSet[] | null>(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<DjSet | null>(null);
  const jobs = useJobs();

  const STATUS: Record<DjSet["status"], { tone: "success" | "info" | "danger" | "neutral"; label: string }> = {
    done: { tone: "success", label: t.shazam.statusDone },
    identifying: { tone: "info", label: t.shazam.statusIdentifying },
    error: { tone: "danger", label: t.shazam.statusError },
    pending: { tone: "neutral", label: t.shazam.statusPending },
  };

  const reload = useCallback(() => {
    listDjSets().then(setSets).catch((e) => setError(errText(e)));
  }, []);

  useEffect(() => {
    shazamStatus().then((s) => setAvailable(s.available)).catch(() => setAvailable(false));
    reload();
  }, [reload]);

  // Il job di identificazione gira nel poller globale (barra job): quando finisce
  // (running -> done) la lista è stantia, ricarica in automatico; su errore lo mostra qui
  // (stesso effetto che prima produceva il polling locale).
  const prevIdentifyStatus = useRef<string | null>(null);
  useEffect(() => {
    const status = jobs.shazamIdentify?.status ?? null;
    if (prevIdentifyStatus.current === "running" && status === "done") {
      reload();
    } else if (prevIdentifyStatus.current === "running" && status === "error") {
      setError(jobs.shazamIdentify?.error ?? t.shazam.identifyFailed);
    }
    prevIdentifyStatus.current = status;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobs.shazamIdentify?.status]);

  const identify = async () => {
    const u = url.trim();
    if (!u) return;
    setBusy(true);
    setError(null);
    try {
      const s = await identifyMix(u);
      setUrl("");
      // Il DjSet e' creato in DB subito (status "identifying"): la lista va aggiornata
      // già ora, non solo a job finito, altrimenti il set appena avviato resta invisibile.
      reload();
      if (!s.cached && s.status !== "done") jobs.refresh();
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  };

  const doDelete = async (s: DjSet) => {
    try { await deleteDjSet(s.id); reload(); } catch (e) { setError(errText(e)); }
  };

  const running = jobs.shazamIdentify?.status === "running";

  const marginalia = (
    <div className="space-y-3 text-xs leading-relaxed text-muted">
      <ol className="space-y-2">
        {t.shazam.guideSteps.map((step, i) => (
          <li key={i} className="flex gap-2">
            <span className="tnum shrink-0 text-faint">{i + 1}</span>
            <span>{step}</span>
          </li>
        ))}
      </ol>
      <p className="border-t border-border pt-3">{t.shazam.sourcesNote}</p>
    </div>
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
                      {s.status === "done" && s.aborted_at_seconds != null && (
                        <span title={t.shazam.partialNote(fmtDuration(s.aborted_at_seconds))} className="shrink-0">
                          <Badge tone="warning">{t.shazam.partialBadge}</Badge>
                        </span>
                      )}
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
