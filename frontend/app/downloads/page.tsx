"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Download as DownloadIcon, EyeOff, Link2, Search } from "lucide-react";
import { PageLayout } from "@/components/page-layout";
import { Alert, Badge, Button, Card, EmptyState, Input, Loading, Select } from "@/components/ui";
import { useJobs } from "@/components/jobs-provider";
import { DownloadReviewModal, type ReviewTarget } from "@/components/download-review-modal";
import { LinkLocalFileModal, type LinkTarget } from "@/components/link-local-file-modal";
import { AutoLinkModal } from "@/components/auto-link-modal";
import { ConfirmModal } from "@/components/confirm-modal";
import {
  downloadManual, downloadPending, ignoreDownload, listImportedPlaylists,
  retryPending, searchDownloads, startPlaylistDownload, trackLabel,
  type DownloadCandidate, type Playlist, type Track,
} from "@/lib/api";
import { useT } from "@/lib/i18n";

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

function DownloadsInner() {
  const t = useT();
  const OUTCOME_LABEL: Record<Outcome, string> = {
    not_found: t.downloads.outcomeNotFound,
    needs_review: t.downloads.outcomeNeedsReview,
    failed: t.downloads.outcomeFailed,
  };
  const FILTERS: { key: Filter; label: string }[] = [
    { key: "all", label: t.downloads.filterAll },
    { key: "needs_review", label: t.downloads.filterNeedsReview },
    { key: "not_found", label: t.downloads.filterNotFound },
    { key: "failed", label: t.downloads.filterFailed },
  ];
  // Un solo poller (JobsProvider) per lo stato job; il work-list è persistito.
  const { download: status, refresh } = useJobs();
  const [playlists, setPlaylists] = useState<Playlist[]>([]);
  const [selected, setSelected] = useState("");
  const [pending, setPending] = useState<Track[] | null>(null);
  // Filtro e ricerca persistiti nella query string: lo stato iniziale viene dall'URL
  // (tornando da un dettaglio traccia non si perde nulla) e ogni modifica viene
  // riflessa con router.replace. I default ("all", query vuota) restano fuori dall'URL.
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const filterParam = searchParams.get("filter");
  const [filter, setFilter] = useState<Filter>(
    filterParam === "needs_review" || filterParam === "not_found" || filterParam === "failed"
      ? filterParam
      : "all",
  );
  const [query, setQuery] = useState(searchParams.get("q") ?? "");
  const [results, setResults] = useState<DownloadCandidate[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [review, setReview] = useState<ReviewTarget | null>(null);
  const [linking, setLinking] = useState<LinkTarget | null>(null);
  const [autoLink, setAutoLink] = useState(false);
  const [confirmIgnore, setConfirmIgnore] = useState<Track | null>(null);
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

  // Stato -> URL: replace (non push, niente cronologia inquinata) con un debounce
  // leggero per non riscrivere l'URL a ogni tasto nell'input di ricerca.
  useEffect(() => {
    const params = new URLSearchParams();
    if (filter !== "all") params.set("filter", filter);
    if (query) params.set("q", query);
    const next = params.toString();
    if (next === searchParams.toString()) return;
    const timer = setTimeout(() => {
      router.replace(next ? `${pathname}?${next}` : pathname, { scroll: false });
    }, 300);
    return () => clearTimeout(timer);
  }, [filter, query, pathname, router, searchParams]);

  const available = status?.available ?? true;
  const running = status?.status === "running";
  const rows = (pending ?? []).filter((tr) => filter === "all" || tr.last_download_outcome === filter);
  const count = (k: Filter) => k === "all"
    ? (pending?.length ?? 0)
    : (pending ?? []).filter((tr) => tr.last_download_outcome === k).length;

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
  const ignore = async (tr: Track) => {
    setError(null);
    try { await ignoreDownload(tr.id); refreshPending(); }
    catch (e) { setError(err(e)); }
  };

  return (
    <PageLayout title={t.downloads.pageTitle} meta={pending?.length || status?.total || undefined}>
      <div className="space-y-6">
        {!available && (
          <Alert tone="info">
            {t.downloads.notConfigured}
          </Alert>
        )}
        {error && <Alert tone="danger">⚠ {error}</Alert>}

        {/* 1. Acquisizione da playlist (azione primaria) */}
        <section>
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">{t.downloads.acquisitionHeading}</div>
          <div className="flex flex-wrap items-center gap-2">
            <Select value={selected} onChange={(e) => setSelected(e.target.value)} disabled={!available || running}>
              <option value="">{t.downloads.choosePlaylistOption}</option>
              {playlists.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </Select>
            <Button onClick={start} disabled={!available || running || !selected}>
              <DownloadIcon size={14} /> {t.downloads.downloadPlaylistButton}
            </Button>
          </div>
          {/* Il progresso del job vive nella barra globale in basso (JobsProvider):
              qui non lo duplichiamo. I risultati persistono nella sezione "da sistemare". */}
        </section>

        {/* 2. Download singolo — ricerca manuale su Soulseek */}
        <section>
          <div className="mb-2 text-[10px] uppercase tracking-wider text-muted">
            {t.downloads.singleDownloadHeading}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Input value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runSearch(); }}
              placeholder={t.downloads.searchPlaceholder} disabled={!available} />
            <Button variant="outline" onClick={runSearch} disabled={!available || searching || !query.trim()}>
              <Search size={14} /> {t.downloads.searchButton}
            </Button>
          </div>
          {searching && <Loading label={t.downloads.searchingLabel} />}
          {results && results.length === 0 && !searching && (
            <p className="mt-2 text-sm text-faint">{t.downloads.noSearchResults(query)}</p>
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
                    <DownloadIcon size={13} /> {t.downloads.downloadButton}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* 3. Work-list persistito (il cuore) */}
        <section>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-1.5" role="tablist" aria-label={t.downloads.filterByOutcomeAria}>
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
                  <Link2 size={13} /> {t.downloads.linkAllButton}
                </Button>
                <Button size="sm" variant="outline" onClick={retryAll} disabled={running || !available}>
                  <DownloadIcon size={13} /> {t.downloads.retryAllButton}
                </Button>
              </div>
            )}
          </div>

          {pending === null && <Loading />}
          {pending !== null && rows.length === 0 && (
            <EmptyState icon={<DownloadIcon size={28} />} title={t.downloads.emptyTitle}>
              {t.downloads.emptyBody}
            </EmptyState>
          )}
          {rows.length > 0 && (
            <Card>
              <ul className="divide-y divide-border text-sm">
                {rows.map((tr) => {
                  const outcome = tr.last_download_outcome as Outcome;
                  const hasFile = outcome === "needs_review" && !!tr.last_download_path;
                  const detail = outcome === "failed"
                    ? t.downloads.failedReason(tr.last_download_reason)
                    : tr.last_download_reason;
                  return (
                    <li key={tr.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5">
                      <div className="min-w-0 flex-1">
                        <a href={`/tracks/${tr.id}`} className="block truncate hover:text-fg-strong">{trackLabel(tr)}</a>
                        {detail && <div className="text-xs text-muted">{detail}</div>}
                      </div>
                      <span className="flex shrink-0 flex-wrap items-center gap-2">
                        <Badge tone={OUTCOME_TONE[outcome] ?? "neutral"}>{OUTCOME_LABEL[outcome] ?? outcome}</Badge>
                        <Button size="sm" onClick={() => setReview({ track_id: tr.id, artist: tr.artist, title: tr.title })}>
                          <Search size={13} /> {hasFile ? t.downloads.reviewButton : t.downloads.chooseFileButton}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setLinking({ id: tr.id, artist: tr.artist, title: tr.title })}>
                          <Link2 size={13} /> {t.downloads.linkFileButton}
                        </Button>
                        <Button size="sm" variant="ghost" onClick={() => setConfirmIgnore(tr)}>
                          <EyeOff size={13} /> {t.downloads.ignoreButton}
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
      <ConfirmModal
        open={confirmIgnore !== null}
        message={confirmIgnore ? t.downloads.ignoreConfirm(trackLabel(confirmIgnore)) : ""}
        onConfirm={() => {
          const tr = confirmIgnore;
          setConfirmIgnore(null);
          if (tr) ignore(tr);
        }}
        onClose={() => setConfirmIgnore(null)}
      />
    </PageLayout>
  );
}

// useSearchParams richiede un boundary Suspense sulle pagine statiche (Next 16),
// stesso pattern di library/set-builder/discovery.
export default function DownloadsPage() {
  return <Suspense><DownloadsInner /></Suspense>;
}
