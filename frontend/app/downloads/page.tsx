"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download as DownloadIcon } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EmptyState, Progress, Select } from "@/components/ui";
import {
  downloadStatus,
  listImportedPlaylists,
  startPlaylistDownload,
  type DownloadStatus,
  type Playlist,
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
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [status, setStatus] = useState<DownloadStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const poll = useCallback(() => {
    downloadStatus()
      .then((s) => alive.current && setStatus(s))
      .catch(() => {
        /* backend offline: ignora */
      });
  }, []);

  useEffect(() => {
    alive.current = true;
    listImportedPlaylists()
      .then((p) => alive.current && setPlaylists(p))
      .catch(() => undefined);
    const id = setInterval(poll, 2000);
    return () => {
      alive.current = false;
      clearInterval(id);
    };
  }, [poll]);

  const start = async () => {
    if (!selected) return;
    setError(null);
    try {
      setStatus(await startPlaylistDownload(Number(selected)));
    } catch (e) {
      setError(err(e));
    }
  };

  const available = status?.available ?? true;
  const running = status?.status === "running";
  const pct = status && status.total > 0 ? (status.processed / status.total) * 100 : 0;

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

        {error && <Alert tone="danger">⚠ {error}</Alert>}

        {status && status.total > 0 && (
          <Card className="p-3">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="tnum">{status.processed}/{status.total}</span>
              <Badge tone="success">{status.downloaded} scaricate</Badge>
              <Badge tone="warning">{status.needs_review} da rivedere</Badge>
              <Badge tone="neutral">{status.not_found} non trovate</Badge>
              <Badge tone="danger">{status.failed} fallite</Badge>
            </div>
            <Progress value={pct} />
            <ul className="mt-3 divide-y divide-border text-sm">
              {status.items.map((it) => (
                <li key={it.track_id} className="flex items-center justify-between gap-3 py-1.5">
                  <span className="truncate">{it.artist ?? "Artista sconosciuto"} — {it.title ?? "Senza titolo"}</span>
                  <Badge tone={OUTCOME_TONE[it.outcome] ?? "neutral"}>{OUTCOME_LABEL[it.outcome] ?? it.outcome}</Badge>
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
    </PageLayout>
  );
}
