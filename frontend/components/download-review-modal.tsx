"use client";

import { useEffect, useState } from "react";
import { Check, Download as DownloadIcon, Trash2 } from "lucide-react";
import { Alert, Button, Loading, Modal, Spinner } from "@/components/ui";
import {
  discardReview, downloadCandidates, downloadReview, downloadTrack, fmtDuration,
  keepReview, type DownloadCandidate, type DownloadReview,
} from "@/lib/api";

export type ReviewTarget = { track_id: number; artist: string | null; title: string | null };

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

function fmtSize(bytes: number | null): string {
  if (!bytes) return "";
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
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

/** Modal di revisione: file dubbio (Tieni/Scarta) + candidati Soulseek (Sostituisci). */
function ReviewDialog({ target, onClose, onPicked }: {
  target: ReviewTarget;
  onClose: () => void;
  onPicked: () => void;
}) {
  const [review, setReview] = useState<DownloadReview | null>(null);
  const [candidates, setCandidates] = useState<DownloadCandidate[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const rev = await downloadReview(target.track_id);
        if (!alive) return;
        setReview(rev);
        const found = await downloadCandidates(
          rev.expected.artist ?? target.artist ?? "",
          rev.expected.title ?? target.title ?? "",
          rev.expected.duration_seconds);
        if (!alive) return;
        setCandidates(found);
      } catch (e) {
        if (!alive) return;
        setError(err(e));
        setCandidates([]);
      }
    })();
    return () => { alive = false; };
  }, [target]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onPicked();
    } catch (e) {
      // 409 tipico: "Un download e' gia' in corso" — riprova a job finito.
      setError(err(e));
    } finally {
      setBusy(false);
    }
  };

  const exp = review?.expected;
  const dl = review?.downloaded;
  const expDur = exp?.duration_seconds ?? null;
  const dlDur = dl?.duration_seconds ?? null;
  const delta = expDur != null && dlDur != null ? dlDur - expDur : null;

  return (
    <Modal open onClose={onClose} title="Rivedi il download" size="lg">
      <div className="space-y-4 p-4">
        <p className="text-sm text-muted">
          {exp?.artist ?? target.artist ?? "?"} — {exp?.title ?? target.title ?? "?"}
          {expDur != null && (
            <span className="ml-2 text-xs text-faint">durata attesa {fmtDuration(expDur)}</span>
          )}
        </p>
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        {dl && (
          <div className="border border-border-strong p-3">
            <div className="mb-1.5 text-[10px] uppercase tracking-wider text-muted">
              File già scaricato
            </div>
            <div className="truncate font-mono text-xs">{dl.name}</div>
            <div className="mt-0.5 text-xs text-muted">
              {(dl.format ?? "?").toUpperCase()}
              {dl.bitrate ? ` · ${dl.bitrate} kbps` : ""}
              {dl.duration_seconds != null ? ` · ${fmtDuration(dl.duration_seconds)}` : ""}
              {delta != null && (
                <span className="ml-1 text-fg-strong">
                  ({delta > 0 ? "+" : ""}{delta}s vs atteso)
                </span>
              )}
              {dl.size ? ` · ${fmtSize(dl.size)}` : ""}
            </div>
            <div className="mt-2 flex gap-2">
              <Button size="sm" onClick={() => run(() => keepReview(target.track_id))} disabled={busy}>
                {busy ? <Spinner /> : <Check size={13} />} Tieni comunque
              </Button>
              <Button size="sm" variant="danger"
                onClick={() => run(() => discardReview(target.track_id))} disabled={busy}>
                <Trash2 size={13} /> Scarta
              </Button>
            </div>
          </div>
        )}

        <div>
          <div className="mb-1.5 text-[10px] uppercase tracking-wider text-muted">
            {dl ? "Oppure sostituisci con" : "Scegli un file"}
          </div>
          {candidates === null && <Loading label="Cerco i candidati su Soulseek…" />}
          {candidates?.length === 0 && (
            <p className="py-6 text-center text-sm text-muted">
              Nessun candidato in questo momento: riprova più tardi (dipende da chi è online).
            </p>
          )}
          {candidates && candidates.length > 0 && (
            <ul className="max-h-72 divide-y divide-border overflow-y-auto border border-border">
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
                  <Button size="sm" variant="outline"
                    onClick={() => run(() => downloadTrack(target.track_id, c))} disabled={busy}>
                    {busy ? <Spinner /> : <DownloadIcon size={13} />} Scarica
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </Modal>
  );
}
