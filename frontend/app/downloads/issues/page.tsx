"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, Download as DownloadIcon, EyeOff, Link2, Search } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EmptyState, Loading } from "@/components/ui";
import { useJobs } from "@/components/jobs-provider";
import { DownloadReviewModal, type ReviewTarget } from "@/components/download-review-modal";
import { LinkLocalFileModal, type LinkTarget } from "@/components/link-local-file-modal";
import { downloadPending, ignoreDownload, retryPending, trackLabel, type Track } from "@/lib/api";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

type Outcome = "not_found" | "needs_review" | "failed";
type Filter = "all" | Outcome;

const OUTCOME_TONE: Record<Outcome, "warning" | "danger" | "neutral"> = {
  not_found: "neutral",
  needs_review: "warning",
  failed: "danger",
};

const OUTCOME_LABEL: Record<Outcome, string> = {
  not_found: "non trovata",
  needs_review: "da rivedere",
  failed: "fallita",
};

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Tutti" },
  { key: "not_found", label: "Non trovate" },
  { key: "needs_review", label: "Da rivedere" },
  { key: "failed", label: "Fallite" },
];

export default function DownloadIssuesPage() {
  const { download: status, refresh } = useJobs();
  const [pending, setPending] = useState<Track[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [linking, setLinking] = useState<LinkTarget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const refreshPending = useCallback(() => {
    downloadPending()
      .then((rows) => alive.current && setPending(rows))
      .catch((e) => alive.current && setError(err(e)));
  }, []);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  // Gli esiti cambiano man mano che il job li produce.
  useEffect(() => { refreshPending(); }, [refreshPending, status?.status, status?.processed]);

  const ignore = async (t: Track) => {
    if (!window.confirm(`Ignorare «${trackLabel(t)}»? Uscirà da questo archivio.`)) return;
    setError(null);
    try {
      await ignoreDownload(t.id);
      refreshPending();
    } catch (e) {
      setError(err(e));
    }
  };

  const retryAll = async () => {
    setError(null);
    try {
      await retryPending();
      refresh();
    } catch (e) {
      setError(err(e));
    }
  };

  const running = status?.status === "running";
  const available = status?.available ?? true;
  const rows = (pending ?? []).filter(
    (t) => filter === "all" || t.last_download_outcome === filter);
  const count = (k: Filter) => k === "all"
    ? (pending?.length ?? 0)
    : (pending ?? []).filter((t) => t.last_download_outcome === k).length;

  return (
    <PageLayout title="Download da sistemare" meta={pending?.length || undefined}>
      <Link href="/downloads" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Download
      </Link>

      <div className="space-y-3">
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-1.5">
            {FILTERS.map((f) => (
              <Button key={f.key} size="sm"
                variant={filter === f.key ? "primary" : "outline"}
                onClick={() => setFilter(f.key)}>
                {f.label} ({count(f.key)})
              </Button>
            ))}
          </div>
          <Button size="sm" variant="outline" onClick={retryAll} disabled={running || !available}>
            <DownloadIcon size={13} /> Riprova tutte
          </Button>
        </div>

        {pending === null && <Loading />}
        {pending !== null && rows.length === 0 && (
          <EmptyState icon={<DownloadIcon size={28} />} title="Niente da sistemare">
            Le tracce con download non trovato, da rivedere o fallito compariranno qui.
          </EmptyState>
        )}
        {rows.length > 0 && (
          <Card>
            <ul className="divide-y divide-border text-sm">
              {rows.map((t) => (
                <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
                  <div className="min-w-0 flex-1">
                    <Link href={`/tracks/${t.id}`} className="truncate hover:text-fg-strong">
                      {trackLabel(t)}
                    </Link>
                    {t.last_download_reason && (
                      <div className="text-xs text-muted">{t.last_download_reason}</div>
                    )}
                  </div>
                  <span className="flex shrink-0 flex-wrap items-center gap-2">
                    <Badge tone={OUTCOME_TONE[t.last_download_outcome as Outcome] ?? "neutral"}>
                      {OUTCOME_LABEL[t.last_download_outcome as Outcome] ?? t.last_download_outcome}
                    </Badge>
                    <Button size="sm" variant="outline"
                      onClick={() => setReview({ track_id: t.id, artist: t.artist, title: t.title })}>
                      <Search size={13} /> Scegli file
                    </Button>
                    <Button size="sm" variant="outline"
                      onClick={() => setLinking({ id: t.id, artist: t.artist, title: t.title })}>
                      <Link2 size={13} /> Collega file
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => ignore(t)}>
                      <EyeOff size={13} /> Ignora
                    </Button>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>

      <DownloadReviewModal
        target={review}
        onClose={() => setReview(null)}
        onPicked={() => {
          refresh();
          setReview(null);
          refreshPending();
        }}
      />
      <LinkLocalFileModal
        target={linking}
        onClose={() => setLinking(null)}
        onLinked={() => refreshPending()}
      />
    </PageLayout>
  );
}
