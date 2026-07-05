"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Download as DownloadIcon, Search, Wrench } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EmptyState, Input, Select, Loading } from "@/components/ui";
import { useJobs } from "@/components/jobs-provider";
import { DownloadReviewModal, type ReviewTarget } from "@/components/download-review-modal";
import {
  downloadManual,
  downloadPending,
  retryPending,
  listImportedPlaylists,
  searchDownloads,
  startPlaylistDownload,
  type DownloadCandidate,
  type Playlist,
  type Track,
} from "@/lib/api";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

const OUTCOME_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  downloaded: "success",
  needs_review: "warning",
  not_found: "neutral",
  failed: "danger",
};

const OUTCOME_LABEL: Record<string, string> = {
  downloaded: "scaricata",
  needs_review: "da rivedere",
  not_found: "non trovata",
  failed: "fallita",
};

export default function DownloadsPage() {
  // Lo stato del job arriva dal poller globale (JobsProvider): niente polling qui.
  const { download: status, refresh } = useJobs();
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DownloadCandidate[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [pending, setPending] = useState<Track[] | null>(null);
  const alive = useRef(true);

  const refreshPending = useCallback(() => {
    downloadPending()
      .then((rows) => alive.current && setPending(rows))
      .catch(() => {
        /* backend offline: ignora */
      });
  }, []);

  // Le "da sistemare" cambiano man mano che il job produce esiti.
  useEffect(() => { refreshPending(); }, [refreshPending, status?.status, status?.processed]);

  useEffect(() => {
    alive.current = true;
    listImportedPlaylists()
      .then((p) => alive.current && setPlaylists(p))
      .catch(() => undefined);
    return () => {
      alive.current = false;
    };
  }, []);

  const retryAll = async () => {
    setError(null);
    try {
      await retryPending();
      refresh();
    } catch (e) {
      setError(err(e));
    }
  };

  const start = async () => {
    if (!selected) return;
    setError(null);
    try {
      await startPlaylistDownload(Number(selected));
      refresh();
    } catch (e) {
      setError(err(e));
    }
  };

  const runSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setSearching(true);
    setError(null);
    setResults(null);
    try {
      setResults(await searchDownloads(q));
    } catch (e) {
      setError(err(e));
    } finally {
      setSearching(false);
    }
  };

  const grab = async (c: DownloadCandidate) => {
    setError(null);
    try {
      await downloadManual(c);
      refresh();
    } catch (e) {
      setError(err(e));
    }
  };

  const available = status?.available ?? true;
  const running = status?.status === "running";
  const count = (k: string) =>
    (pending ?? []).filter((t) => t.last_download_outcome === k).length;

  return (
    <PageLayout title="Download" meta={status?.total || undefined}>
      <div className="space-y-3">
        {!available && (
          <Alert tone="info">
            slskd non e&apos; configurato. Imposta SLSKD_URL, SLSKD_API_KEY e
            SLSKD_DOWNLOAD_DIR in backend/.env per abilitare i download.
          </Alert>
        )}

        <Card className="flex items-center gap-3 p-3">
          <Select
            value={selected}
            onChange={(e) => setSelected(e.target.value)}
            disabled={!available || running}
          >
            <option value="">Scegli una playlist…</option>
            {playlists.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </Select>
          <Button onClick={start} disabled={!available || running || !selected}>
            <DownloadIcon size={14} /> Scarica playlist
          </Button>
        </Card>

        <Card className="p-3">
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">Ricerca manuale</div>
          <div className="flex items-center gap-2">
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") runSearch();
              }}
              placeholder="Cerca su Soulseek (artista, titolo…)"
              disabled={!available}
            />
            <Button
              variant="outline"
              onClick={runSearch}
              disabled={!available || searching || !query.trim()}
            >
              <Search size={14} /> Cerca
            </Button>
          </div>
          {searching && <Loading label="Ricerca su Soulseek…" />}
          {results && results.length === 0 && !searching && (
            <p className="mt-2 text-sm text-faint">Nessun risultato per «{query}».</p>
          )}
          {results && results.length > 0 && (
            <ul className="mt-3 divide-y divide-border">
              {results.slice(0, 40).map((c, i) => (
                <li key={`${c.username}-${i}`} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm">{c.filename.split(/[\\/]/).pop()}</div>
                    <div className="text-xs text-faint">
                      {c.format?.toUpperCase()}
                      {c.bitrate ? ` · ${c.bitrate}kbps` : ""} · {c.username}
                    </div>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => grab(c)} disabled={running}>
                    <DownloadIcon size={13} /> Scarica
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {error && <Alert tone="danger">⚠ {error}</Alert>}

        {pending && pending.length > 0 && (
          <Card className="p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-[10px] uppercase tracking-wider text-muted">
                Da sistemare ({pending.length})
              </span>
              <span className="flex items-center gap-2">
                <Button size="sm" variant="outline" onClick={retryAll} disabled={running || !available}>
                  <DownloadIcon size={13} /> Riprova tutte
                </Button>
                <Link href="/downloads/issues">
                  <Button size="sm" variant="outline">
                    <Wrench size={13} /> Vai all&apos;archivio
                  </Button>
                </Link>
              </span>
            </div>
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge tone="neutral">{count("not_found")} non trovate</Badge>
              <Badge tone="warning">{count("needs_review")} da rivedere</Badge>
              <Badge tone="danger">{count("failed")} fallite</Badge>
            </div>
          </Card>
        )}

        {status && status.total > 0 && (
          <Card className="p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="tnum">{status.processed}/{status.total}</span>
              <Badge tone="success">{status.downloaded} scaricate</Badge>
              <Badge tone="warning">{status.needs_review} da rivedere</Badge>
              <Badge tone="neutral">{status.not_found} non trovate</Badge>
              <Badge tone="danger">{status.failed} fallite</Badge>
            </div>
            <ul className="mt-3 divide-y divide-border text-sm">
              {status.items.map((it) => (
                <li key={it.track_id} className="flex items-center justify-between gap-3 py-1.5">
                  <span className="truncate">
                    {it.artist ?? "Artista sconosciuto"} — {it.title ?? "Senza titolo"}
                    {it.reason && <span className="ml-2 text-xs text-muted">({it.reason})</span>}
                  </span>
                  <span className="flex shrink-0 items-center gap-2">
                    {it.outcome !== "downloaded" && it.track_id != null && (
                      <Button size="sm" variant="outline" onClick={() => setReview(it)}>
                        <Search size={13} /> Scegli file
                      </Button>
                    )}
                    <Badge tone={OUTCOME_TONE[it.outcome] ?? "neutral"}>{OUTCOME_LABEL[it.outcome] ?? it.outcome}</Badge>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
        )}

        {status && status.total === 0 && available && (
          <EmptyState icon={<DownloadIcon size={28} />} title="Nessun download">
            Scegli una playlist e avvia il download.
          </EmptyState>
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
    </PageLayout>
  );
}
