"use client";

import { useEffect, useState } from "react";
import { Check, Disc3, Download, ExternalLink } from "lucide-react";
import {
  discoveryImportTrack, discoverySaveForLater, downloadTrackAuto, fmtDuration, getDiscogsRelease,
  type DiscogsRelease, type DiscoveryLead,
} from "@/lib/api";
import { Alert, Button, Modal, Spinner } from "@/components/ui";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

type PanelTrack = { position: string; title: string; duration_seconds: number | null };

export function DiscoveryTracklistPanel({ lead, onClose }: {
  lead: DiscoveryLead | null;
  onClose: () => void;
}) {
  const [release, setRelease] = useState<DiscogsRelease | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!lead?.discogs_id) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- resets stale release when the modal closes/switches to a lead without a discogs_id
      setRelease(null);
      return;
    }
    setLoading(true);
    setError(null);
    setRelease(null);
    getDiscogsRelease(lead.discogs_id)
      .then(setRelease)
      .catch((e) => setError(err(e)))
      .finally(() => setLoading(false));
  }, [lead?.discogs_id]);

  const tracks: PanelTrack[] = release
    ? release.tracks.length
      ? release.tracks
      : [{ position: "", title: release.title, duration_seconds: null }]
    : [];

  return (
    <Modal
      open={lead !== null}
      onClose={onClose}
      title={lead ? `${lead.artist} — ${lead.title}` : undefined}
      size="lg"
    >
      {error && <Alert tone="danger">⚠ {error}</Alert>}
      {loading && (
        <p className="flex items-center gap-2 py-6 text-sm text-muted">
          <Spinner /> Carico la tracklist…
        </p>
      )}
      {release && (
        <div>
          <div className="mb-3 flex items-center justify-between gap-3 border-b border-border pb-3">
            <div className="flex min-w-0 items-center gap-2 text-xs text-faint">
              {release.thumb_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={release.thumb_url} alt="" className="h-10 w-10 shrink-0 border border-border object-cover" />
              ) : (
                <div className="grid h-10 w-10 shrink-0 place-items-center border border-border bg-elevated text-faint">
                  <Disc3 size={16} />
                </div>
              )}
              <div className="min-w-0">
                {release.label && <span className="truncate">{release.label}</span>}
                {release.year != null && <span> · {release.year}</span>}
                {release.discogs_url && (
                  <a
                    href={release.discogs_url}
                    target="_blank"
                    rel="noreferrer"
                    className="ml-2 inline-flex items-center gap-1 text-fg hover:underline"
                  >
                    <ExternalLink size={12} /> Discogs
                  </a>
                )}
              </div>
            </div>
            <SaveAllButton release={release} tracks={tracks} />
          </div>
          <ul className="divide-y divide-border">
            {tracks.map((t, i) => (
              <TrackRow key={`${t.position}-${t.title}-${i}`} release={release} track={t} />
            ))}
          </ul>
        </div>
      )}
    </Modal>
  );
}

function SaveAllButton({ release, tracks }: { release: DiscogsRelease; tracks: PanelTrack[] }) {
  const [saving, setSaving] = useState(false);
  const [done, setDone] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const saveAll = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      for (const t of tracks) {
        await discoverySaveForLater({
          artist: release.artist, title: t.title, duration_seconds: t.duration_seconds,
          album_art_url: release.thumb_url, url: release.discogs_url,
        });
      }
      setDone(true);
    } catch (e) {
      setSaveError(err(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="shrink-0 text-right">
      <Button size="sm" variant={done ? "ghost" : "outline"} onClick={saveAll} disabled={saving || done}>
        {done ? <><Check size={14} /> Tutte salvate</> : saving ? <Spinner /> : "Tutte per dopo"}
      </Button>
      {saveError && <p className="mt-1 text-xs text-danger">⚠ {saveError}</p>}
    </div>
  );
}

function TrackRow({ release, track }: { release: DiscogsRelease; track: PanelTrack }) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloaded, setDownloaded] = useState(false);
  const [rowError, setRowError] = useState<string | null>(null);

  const input = {
    artist: release.artist, title: track.title, duration_seconds: track.duration_seconds,
    album_art_url: release.thumb_url, url: release.discogs_url,
  };

  const saveForLater = async () => {
    setSaving(true);
    setRowError(null);
    try {
      await discoverySaveForLater(input);
      setSaved(true);
    } catch (e) {
      setRowError(err(e));
    } finally {
      setSaving(false);
    }
  };

  const downloadNow = async () => {
    setDownloading(true);
    setRowError(null);
    try {
      const { track: imported } = await discoveryImportTrack(input);
      await downloadTrackAuto(imported.id);
      setDownloaded(true);
    } catch (e) {
      setRowError(err(e));
    } finally {
      setDownloading(false);
    }
  };

  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <div className="min-w-0">
        <div className="truncate text-sm text-fg">
          {track.position && <span className="tnum text-faint">{track.position} · </span>}
          {track.title}
        </div>
        <div className="tnum text-xs text-faint">{fmtDuration(track.duration_seconds)}</div>
        {rowError && <p className="mt-0.5 text-xs text-danger">⚠ {rowError}</p>}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        <Button size="sm" variant={saved ? "ghost" : "outline"} onClick={saveForLater} disabled={saving || saved}>
          {saved ? <Check size={14} /> : saving ? <Spinner /> : "Per dopo"}
        </Button>
        <Button size="sm" variant={downloaded ? "ghost" : "outline"} onClick={downloadNow} disabled={downloading || downloaded}>
          {downloaded ? <><Check size={14} /> In coda</> : downloading ? <Spinner /> : <><Download size={13} /> Scarica ora</>}
        </Button>
      </div>
    </li>
  );
}
