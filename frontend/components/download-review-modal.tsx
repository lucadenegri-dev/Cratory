"use client";

import { useEffect, useState } from "react";
import { Download as DownloadIcon } from "lucide-react";
import { Alert, Button, Loading, Modal, Spinner } from "@/components/ui";
import {
  apiGet, downloadCandidates, downloadTrack, fmtDuration,
  type DownloadCandidate, type TrackDetail,
} from "@/lib/api";

export type ReviewTarget = { track_id: number; artist: string | null; title: string | null };

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

/** Wrapper: monta il dialog solo con un target e lo rigenera per ogni traccia. */
export function DownloadReviewModal({ target, onClose, onPicked }: {
  target: ReviewTarget | null;
  onClose: () => void;
  onPicked: () => void;
}) {
  if (!target) return null;
  return <ReviewDialog key={target.track_id} target={target} onClose={onClose} onPicked={onPicked} />;
}

/** Modal "Scegli il file": candidati Soulseek per una traccia da sistemare. */
function ReviewDialog({ target, onClose, onPicked }: {
  target: ReviewTarget;
  onClose: () => void;
  onPicked: () => void;
}) {
  const [candidates, setCandidates] = useState<DownloadCandidate[] | null>(null);
  const [duration, setDuration] = useState<number | null>(null);
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        // La durata attesa aiuta il ranking dei candidati (bonus/penalita' via backend).
        const track = await apiGet<TrackDetail>(`/api/tracks/${target.track_id}`);
        if (!alive) return;
        setDuration(track.duration_seconds);
        const found = await downloadCandidates(
          track.artist ?? target.artist ?? "", track.title ?? target.title ?? "",
          track.duration_seconds);
        if (!alive) return;
        setCandidates(found);
      } catch (e) {
        if (!alive) return;
        setError(err(e));
        setCandidates([]);
      }
    })();
    return () => {
      alive = false;
    };
  }, [target]);

  const pick = async (c: DownloadCandidate) => {
    setPicking(true);
    setError(null);
    try {
      await downloadTrack(target.track_id, c);
      onPicked();
    } catch (e) {
      // 409 tipico: "Un download e' gia' in corso" — riprova a job finito.
      setError(err(e));
    } finally {
      setPicking(false);
    }
  };

  return (
    <Modal open onClose={onClose} title="Scegli il file" size="lg">
      <div className="p-4">
        <p className="mb-3 text-sm text-muted">
          {target.artist ?? "?"} — {target.title ?? "?"}
          {duration != null && (
            <span className="ml-2 text-xs text-faint">durata attesa {fmtDuration(duration)}</span>
          )}
        </p>
        {error && <Alert tone="danger">⚠ {error}</Alert>}
        {candidates === null && <Loading label="Cerco i candidati su Soulseek…" />}
        {candidates?.length === 0 && (
          <p className="py-6 text-center text-sm text-muted">
            Nessun candidato in questo momento: riprova più tardi (dipende da chi è online).
          </p>
        )}
        {candidates && candidates.length > 0 && (
          <ul className="max-h-80 divide-y divide-border overflow-y-auto border border-border">
            {candidates.map((c, i) => (
              <li key={`${c.username}-${i}`} className="flex items-center gap-3 px-3 py-2 text-sm">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-xs">{c.filename.split("\\").pop()}</div>
                  <div className="mt-0.5 text-xs text-muted">
                    {(c.format ?? "?").toUpperCase()}
                    {c.bitrate ? ` · ${c.bitrate} kbps` : ""}
                    {c.length ? ` · ${fmtDuration(c.length)}` : ""}
                    {" · "}{c.username}
                    {" · "}<span className="tnum">{c.confidence}</span>/100
                  </div>
                </div>
                <Button size="sm" onClick={() => pick(c)} disabled={picking}>
                  {picking ? <Spinner /> : <DownloadIcon size={13} />} Scarica
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}
