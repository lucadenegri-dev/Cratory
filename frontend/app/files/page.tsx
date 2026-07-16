"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listFiles, libraryStats, listSources, libraryFacets, deleteSource,
  type FileRow, type LibraryStats, type LibraryFacets, type ScanRoot, type FileQuery,
} from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { FilesTable } from "@/components/files-table";
import { SourceMenu } from "@/components/source-menu";
import { Alert, Button, EmptyState, Input, Loading, Select, Spinner } from "@/components/ui";
import { useT } from "@/lib/i18n";

const LIMIT = 500;

// campi tag filtrabili (il placeholder è risolto da t.files.facet*)
const FACET_KEYS: (keyof LibraryFacets)[] = ["genre", "artist", "album", "label", "ext", "year"];

function facetOptions(facets: LibraryFacets | null, key: keyof LibraryFacets): string[] {
  if (!facets) return [];
  return facets[key].map((v) => String(v));
}

function FacetInput({ facet, placeholder, value, options, onChange }: {
  facet: string;
  placeholder: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  const listId = `facet-${facet}`;
  return (
    <>
      <input
        list={listId} value={value} placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="w-32 border border-border bg-bg px-2 py-1 text-[11px] text-fg-strong placeholder:text-faint focus:border-border-strong focus:outline-none"
      />
      <datalist id={listId}>
        {options.map((o) => <option key={o} value={o} />)}
      </datalist>
    </>
  );
}

export default function FilesPage() {
  const t = useT();
  const { scan, startScan, refresh } = useJobs();
  const [rows, setRows] = useState<FileRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [roots, setRoots] = useState<ScanRoot[]>([]);
  const [offline, setOffline] = useState(false);

  const [rootId, setRootId] = useState<string>("");
  const [onlyIssues, setOnlyIssues] = useState(false);
  const [sort, setSort] = useState<FileQuery["sort"]>("path");
  const [q, setQ] = useState("");
  const [facets, setFacets] = useState<LibraryFacets | null>(null);
  const [tag, setTag] = useState<Record<string, string>>({
    genre: "", artist: "", album: "", label: "", ext: "", year: "",
  });
  const setTagField = (k: string, v: string) => setTag((prev) => ({ ...prev, [k]: v }));

  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const loadRoots = useCallback(() => {
    listSources().then(setRoots).catch(() => {});
  }, []);

  const selectedRoot = rootId ? roots.find((r) => r.id === Number(rootId)) ?? null : null;
  const running = scan.status === "running";

  const onScan = async () => {
    setActionError(null);
    try {
      await startScan(rootId ? [Number(rootId)] : undefined);
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.sources.scanStartFailed);
    }
  };
  const onScanRoot = async (id: number) => {
    setActionError(null);
    try {
      await startScan([id]);
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.sources.scanStartFailed);
    }
  };
  const onDeleteRoot = async (id: number) => {
    if (deletingId !== null) return;
    setActionError(null);
    setDeletingId(id);
    try {
      await deleteSource(id);
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.sources.rootRemoveFailed);
    } finally {
      setDeletingId(null);
      loadRoots();
    }
  };

  const facetPlaceholder: Record<string, string> = {
    genre: t.files.facetGenre, artist: t.files.facetArtist, album: t.files.facetAlbum,
    label: t.files.facetLabel, ext: t.files.facetExt, year: t.files.facetYear,
  };

  const load = useCallback(() => {
    const query: FileQuery = {
      root_id: rootId ? Number(rootId) : undefined,
      has_issues: onlyIssues ? true : undefined,
      sort,
      q: q.trim() || undefined,
      genre: tag.genre || undefined,
      artist: tag.artist || undefined,
      album: tag.album || undefined,
      label: tag.label || undefined,
      ext: tag.ext || undefined,
      year: tag.year ? Number(tag.year) : undefined,
      limit: LIMIT,
    };
    listFiles(query)
      .then((r) => { setRows(r); setOffline(false); })
      .catch(() => setOffline(true))
      .finally(() => setLoaded(true));
    libraryStats().then(setStats).catch(() => setStats(null));
  }, [rootId, onlyIssues, sort, q, tag]);

  useEffect(() => { loadRoots(); }, [loadRoots]);
  useEffect(() => { libraryFacets().then(setFacets).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (scan.status === "done") { load(); libraryFacets().then(setFacets).catch(() => {}); }
  }, [scan.status, load]);

  return (
    <PageLayout
      title="Files"
      meta={stats ? (stats.files_total > rows.length ? t.files.metaOf(rows.length, stats.files_total) : String(rows.length)) : undefined}
      marginaliaTitle={t.files.library}
      marginalia={<Marginalia stats={stats} />}
      guide={<>
        <p>{t.sources.guideFolders}</p>
        <p>{t.files.guide2}</p>
        <p>{t.files.guide3}</p>
      </>}
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>{t.common.backendOffline}</Alert>}
        {actionError && <Alert>{actionError}</Alert>}

        <div className="flex flex-wrap items-center gap-2">
          <SourceMenu
            roots={roots}
            selectedId={rootId ? Number(rootId) : null}
            onSelect={(id) => setRootId(id === null ? "" : String(id))}
            onScanRoot={onScanRoot}
            onDelete={onDeleteRoot}
            onAdded={loadRoots}
            deletingId={deletingId}
          />
          <Button onClick={onScan} disabled={running || roots.length === 0}>
            {running && <Spinner />}
            {running
              ? t.sources.scanning
              : selectedRoot
                ? t.files.scanOne(selectedRoot.label || selectedRoot.path)
                : t.files.scanAll}
          </Button>
          <Select value={onlyIssues ? "issues" : "all"} onChange={(e) => setOnlyIssues(e.target.value === "issues")} className="w-auto">
            <option value="all">{t.files.filterAll}</option>
            <option value="issues">{t.files.filterIssues}</option>
          </Select>
          <Select value={sort} onChange={(e) => setSort(e.target.value as FileQuery["sort"])} className="w-auto">
            <option value="path">{t.files.sortPath}</option>
            <option value="artist">{t.files.sortArtist}</option>
            <option value="title">{t.files.sortTitle}</option>
            <option value="bitrate">{t.files.sortBitrate}</option>
            <option value="duration">{t.files.sortDuration}</option>
          </Select>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.files.searchPlaceholder} className="w-48" />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {FACET_KEYS.map((key) => (
            <FacetInput
              key={key} facet={key} placeholder={facetPlaceholder[key]} value={tag[key]}
              options={facetOptions(facets, key)}
              onChange={(v) => setTagField(key, v)}
            />
          ))}
          {Object.values(tag).some(Boolean) && (
            <button
              onClick={() => setTag({ genre: "", artist: "", album: "", label: "", ext: "", year: "" })}
              className="border border-border px-2 py-1 text-[11px] text-muted hover:bg-elevated"
            >{t.files.clearFilters}</button>
          )}
        </div>

        {scan.result && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 border border-border px-3 py-2 text-[11px]">
            <ScanStat k={t.sources.statFound} v={scan.result.found} />
            <ScanStat k={t.sources.statNew} v={`+${scan.result.inserted}`} />
            <ScanStat k={t.sources.statUpdated} v={scan.result.updated} />
            <ScanStat k={t.sources.statMoved} v={scan.result.moved} />
            <ScanStat k={t.sources.statMissing} v={scan.result.missing} />
            <ScanStat k={t.sources.statErrors} v={scan.result.errors} danger={scan.result.errors > 0} />
          </div>
        )}

        {!loaded ? (
          <Loading />
        ) : rows.length === 0 && !offline ? (
          <EmptyState title={t.files.emptyTitle}>{t.files.emptyBody}</EmptyState>
        ) : (
          <FilesTable rows={rows} />
        )}
      </div>
    </PageLayout>
  );
}

function Marginalia({ stats }: { stats: LibraryStats | null }) {
  const t = useT();
  if (!stats) return <p className="text-xs text-faint">{t.common.empty}</p>;
  const sev = stats.issues_by_severity;
  const issuesTotal = Object.values(sev).reduce((a, b) => a + b, 0);
  return (
    <div className="flex flex-col gap-4 text-xs">
      <Stat v={stats.files_total} k={t.files.statFiles} />
      <div>
        <Stat v={issuesTotal} k={t.files.statIssues} />
        <div className="mt-1 flex gap-3 text-[11px]">
          <span className="text-danger">{sev.error ?? 0} {t.files.sevErr}</span>
          <span className="text-warning">{sev.warning ?? 0} {t.files.sevWarn}</span>
          <span className="text-muted">{sev.info ?? 0} {t.files.sevInfo}</span>
        </div>
      </div>
      <Stat v={stats.dup_groups} k={t.files.statDups} />
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">{t.files.formats}</div>
        <div className="flex flex-col gap-1">
          {Object.entries(stats.by_ext).sort((a, b) => b[1] - a[1]).map(([ext, n]) => (
            <div key={ext} className="flex justify-between">
              <span className="text-muted">{ext}</span>
              <span className="tnum text-fg">{n}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Stat({ v, k }: { v: number; k: string }) {
  return (
    <div>
      <div className="tnum text-2xl leading-none text-fg-strong">{v}</div>
      <div className="mt-1 text-[10px] uppercase tracking-wider text-muted">{k}</div>
    </div>
  );
}

function ScanStat({ k, v, danger }: { k: string; v: string | number; danger?: boolean }) {
  return (
    <span className="flex items-center gap-1">
      <span className="text-muted">{k}</span>
      <span className={`tnum ${danger ? "text-danger" : "text-fg"}`}>{v}</span>
    </span>
  );
}
