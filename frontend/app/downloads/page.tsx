"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Download as DownloadIcon, EyeOff, Link2, Search } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EmptyState, EqMeter, Input, Loading, Select } from "@/components/ui";
import { useJobs } from "@/components/jobs-provider";
import { DownloadReviewModal, type ReviewTarget } from "@/components/download-review-modal";
import { LinkLocalFileModal, type LinkTarget } from "@/components/link-local-file-modal";
import { AutoLinkModal } from "@/components/auto-link-modal";
import {
  downloadManual, downloadPending, ignoreDownload, listImportedPlaylists,
  retryPending, searchDownloads, startPlaylistDownload, trackLabel,
  type DownloadCandidate, type Playlist, type Track,
} from "@/lib/api";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

type Outcome = "not_found" | "needs_review" | "failed";
type Filter = "all" | Outcome;

const OUTCOME_LABEL: Record<Outcome, string> = {
  not_found: "non trovata",
  needs_review: "da rivedere",
  failed: "fallita",
};
const OUTCOME_TONE: Record<Outcome, "warning" | "danger" | "neutral"> = {
  not_found: "neutral",
  needs_review: "warning",
  failed: "danger",
};
const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "Tutte" },
  { key: "needs_review", label: "Da rivedere" },
  { key: "not_found", label: "Non trovate" },
  { key: "failed", label: "Fallite" },
];

export default function DownloadsPage() {
  // Un solo poller (JobsProvider) per lo stato job; il work-list è persistito.
  const { download: status, refresh } = useJobs();
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [selected, setSelected] = useState("");
  const [pending, setPending] = useState<Track[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DownloadCandidate[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [linking, setLinking] = useState<LinkTarget | null>(null);
  const [autoLink, setAutoLink] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const refreshPending = useCallback(() => {
    downloadPending()
      .then((rows) => alive.current && setPending(rows))
      .catch(() => alive.current && setPending([]));
  }, []);

  useEffect(() => {
    alive.current = true;
    listImportedPlaylists().then((p) => alive.current && setPlaylists(p)).catch(() => undefined);
    return () => { alive.current = false; };
  }, []);

  // Il work-list cambia man mano che il job produce esiti.
  useEffect(() => { refreshPending(); }, [refreshPending, status?.status, status?.processed]);

  const available = status?.available ?? true;
  const running = status?.status === "running";
  const rows = (pending ?? []).filter((t) => filter === "all" || t.last_download_outcome === filter);
  const count = (k: Filter) => k === "all"
    ? (pending?.length ?? 0)
    : (pending ?? []).filter((t) => t.last_download_outcome === k).length;

  const start = async () => {
    if (!selected) return;
    setError(null);
    try { await startPlaylistDownload(Number(selected)); refresh(); }
    catch (e) { setError(err(e)); }
  };
  const retryAll = async () => {
    setError(null);
    try { await retryPending(); refresh(); }
    catch (e) { setError(err(e)); }
  };
  const runSearch = async () => {
    const q = query.trim();
    if (!q) return;
    setSearching(true); setError(null); setResults(null);
    try { setResults(await searchDownloads(q)); }
    catch (e) { setError(err(e)); }
    finally { setSearching(false); }
  };
  const grab = async (c: DownloadCandidate) => {
    setError(null);
    try { await downloadManual(c); refresh(); }
    catch (e) { setError(err(e)); }
  };
  const ignore = async (t: Track) => {
    if (!window.confirm(`Ignorare «${trackLabel(t)}»? Uscirà da questo elenco.`)) return;
    setError(null);
    try { await ignoreDownload(t.id); refreshPending(); }
    catch (e) { setError(err(e)); }
  };

  return (
    <PageLayout title="Download" meta={pending?.length || status?.total || undefined}>
      <div className="space-y-6">
        {!available && (
          <Alert tone="info">
            slskd non e&apos; configurato. Imposta SLSKD_URL, SLSKD_API_KEY e
            SLSKD_DOWNLOAD_DIR in backend/.env per abilitare i download.
          </Alert>
        )}
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        {/* 1. Acquisizione da playlist (azione primaria) */}
        <section>
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">Acquisizione</div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={selected} onChange={(e) => setSelected(e.target.value)} disabled={!available || running}>
              <option value="">Scegli una playlist…</option>
              {playlists.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
            <Button onClick={start} disabled={!available || running || !selected}>
              <DownloadIcon size={14} /> Scarica playlist
            </Button>
          </div>
          {status && status.total > 0 && (
            <div className="mt-3 border border-border p-3">
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs text-muted">
                <span className="tnum">{status.processed}/{status.total}</span>
                {status.current_label && <span className="truncate">· {status.current_label}</span>}
                <span className="tnum ml-auto">
                  {status.downloaded} scaricate · {status.needs_review + status.not_found + status.failed} da sistemare
                </span>
              </div>
              <EqMeter value={running ? status.processed / Math.max(status.total, 1) : null} />
            </div>
          )}
        </section>

        {/* 2. Download singolo — ricerca manuale su Soulseek */}
        <section>
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">
            Download singolo — scarica un file sul disco (entra in libreria dopo l&apos;organizzazione)
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Input value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
              placeholder="Cerca su Soulseek (artista, titolo…)" disabled={!available} />
            <Button variant="outline" onClick={runSearch} disabled={!available || searching || !query.trim()}>
              <Search size={14} /> Cerca
            </Button>
          </div>
          {searching && <Loading label="Ricerca su Soulseek…" />}
          {results && results.length === 0 && !searching && (
            <p className="mt-2 text-sm text-faint">Nessun risultato per «{query}».</p>
          )}
          {results && results.length > 0 && (
            <ul className="mt-3 divide-y divide-border border border-border">
              {results.slice(0, 40).map((c, i) => (
                <li key={`${c.username}-${i}`} className="flex items-center justify-between gap-3 px-3 py-2">
                  <div className="min-w-0">
                    <div className="truncate text-sm">{c.filename.split(/[\\/]/).pop()}</div>
                    <div className="text-xs text-faint">
                      {c.format?.toUpperCase()}{c.bitrate ? ` · ${c.bitrate}kbps` : ""} · {c.username}
                    </div>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => grab(c)} disabled={running}>
                    <DownloadIcon size={13} /> Scarica
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* 3. Work-list persistito (il cuore) */}
        <section>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Filtra per esito">
              {FILTERS.map((f) => (
                <Button key={f.key} size="sm" role="tab" aria-selected={filter === f.key}
                  variant={filter === f.key ? "primary" : "outline"} onClick={() => setFilter(f.key)}>
                  {f.label} ({count(f.key)})
                </Button>
              ))}
            </div>
            {(pending?.length ?? 0) > 0 && (
              <div className="flex flex-wrap items-center gap-1.5">
                <Button size="sm" variant="outline" onClick={() => setAutoLink(true)}>
                  <Link2 size={13} /> Collega tutte
                </Button>
                <Button size="sm" variant="outline" onClick={retryAll} disabled={running || !available}>
                  <DownloadIcon size={13} /> Riprova tutte
                </Button>
              </div>
            )}
          </div>

          {pending === null && <Loading />}
          {pending !== null && rows.length === 0 && (
            <EmptyState icon={<DownloadIcon size={28} />} title="Niente da sistemare">
              Scegli una playlist e avvia il download; le tracce non trovate, da rivedere o fallite compariranno qui.
            </EmptyState>
          )}
          {rows.length > 0 && (
            <Card>
              <ul className="divide-y divide-border text-sm">
                {rows.map((t) => {
                  const outcome = t.last_download_outcome as Outcome;
                  const hasFile = outcome === "needs_review" && !!t.last_download_path;
                  return (
                    <li key={t.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
                      <div className="min-w-0 flex-1">
                        <a href={`/tracks/${t.id}`} className="block truncate hover:text-fg-strong">{trackLabel(t)}</a>
                        {t.last_download_reason && <div className="text-xs text-muted">{t.last_download_reason}</div>}
                      </div>
                      <span className="flex shrink-0 flex-wrap items-center gap-2">
                        <Badge tone={OUTCOME_TONE[outcome] ?? "neutral"}>{OUTCOME_LABEL[outcome] ?? outcome}</Badge>
                        <Button size="sm" onClick={() => setReview({ track_id: t.id, artist: t.artist, title: t.title })}>
                          <Search size={13} /> {hasFile ? "Rivedi" : "Scegli file"}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setLinking({ id: t.id, artist: t.artist, title: t.title })}>
                          <Link2 size={13} /> Collega file
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => ignore(t)}>
                          <EyeOff size={13} /> Ignora
                        </Button>
                      </span>
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </section>
      </div>

      <DownloadReviewModal
        target={review}
        onClose={() => setReview(null)}
        onPicked={() => { refresh(); setReview(null); refreshPending(); }}
      />
      <LinkLocalFileModal
        target={linking}
        onClose={() => setLinking(null)}
        onLinked={() => { setLinking(null); refreshPending(); }}
      />
      <AutoLinkModal
        open={autoLink}
        onClose={() => setAutoLink(false)}
        onLinked={refreshPending}
      />
    </PageLayout>
  );
}
