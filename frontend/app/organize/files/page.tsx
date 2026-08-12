"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listFiles, libraryStats, libraryFacets,
  type FileRow, type LibraryStats, type LibraryFacets, type Location, type FileQuery,
} from "@/lib/organize/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { FilesTable } from "@/components/organize/files-table";
import { FileEditPanel } from "@/components/organize/file-edit-panel";
import { Alert, Button, EmptyState, Input, Loading, Select, Spinner } from "@/components/ui";
import { useT } from "@/lib/i18n";

const LIMIT = 500;

// campi tag filtrabili (il placeholder è risolto da t.organize.files.facet*)
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
  const [offline, setOffline] = useState(false);

  // F3b: non più un elenco di sorgenti da amministrare, solo un filtro sulle
  // due location fisse (derivate da Settings: LIBRARY_ROOT e SLSKD_DOWNLOAD_DIR).
  const [location, setLocation] = useState<Location | "">("");
  const [onlyIssues, setOnlyIssues] = useState(false);
  const [sort, setSort] = useState<NonNullable<FileQuery["sort"]>>("path");
  const [dir, setDir] = useState<NonNullable<FileQuery["dir"]>>("asc");
  const [q, setQ] = useState("");
  const [facets, setFacets] = useState<LibraryFacets | null>(null);
  const [tag, setTag] = useState<Record<string, string>>({
    genre: "", artist: "", album: "", label: "", ext: "", year: "",
  });
  const setTagField = (k: string, v: string) => setTag((prev) => ({ ...prev, [k]: v }));

  const [actionError, setActionError] = useState<string | null>(null);
  const [editing, setEditing] = useState<FileRow | null>(null);

  const running = scan.status === "running";

  // click su una colonna: se già attiva inverte la direzione, altrimenti ordina asc
  const onSort = (col: NonNullable<FileQuery["sort"]>) => {
    if (sort === col) setDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSort(col); setDir("asc"); }
  };

  const onScan = async () => {
    setActionError(null);
    try {
      await startScan(location ? [location] : undefined);
      refresh();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : t.organize.files.scanStartFailed);
    }
  };

  const facetPlaceholder: Record<string, string> = {
    genre: t.organize.files.facetGenre, artist: t.organize.files.facetArtist, album: t.organize.files.facetAlbum,
    label: t.organize.files.facetLabel, ext: t.organize.files.facetExt, year: t.organize.files.facetYear,
  };

  const load = useCallback(() => {
    const query: FileQuery = {
      location: location || undefined,
      has_issues: onlyIssues ? true : undefined,
      sort,
      dir,
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
  }, [location, onlyIssues, sort, dir, q, tag]);

  useEffect(() => { libraryFacets().then(setFacets).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (scan.status === "done") { load(); libraryFacets().then(setFacets).catch(() => {}); }
  }, [scan.status, load]);

  return (
    <PageLayout
      title="Files"
      meta={stats ? (stats.files_total > rows.length ? t.organize.files.metaOf(rows.length, stats.files_total) : String(rows.length)) : undefined}
      marginaliaTitle={t.organize.files.library}
      marginalia={<Marginalia stats={stats} />}
      guide={<>
        <p>{t.organize.files.guide1}</p>
        <p>{t.organize.files.guide2}</p>
        <p>{t.organize.files.guide3}</p>
      </>}
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>{t.organize.common.backendOffline}</Alert>}
        {actionError && <Alert>{actionError}</Alert>}

        <div className="flex flex-wrap items-center gap-2">
          <Select
            value={location}
            onChange={(e) => setLocation(e.target.value as Location | "")}
            className="h-8 w-36 text-[11px]"
          >
            <option value="">{t.organize.common.all}</option>
            <option value="inbox">{t.organize.files.inbox}</option>
            <option value="library">{t.organize.files.library}</option>
          </Select>
          <Button onClick={onScan} disabled={running || (stats != null && stats.sources === 0)}>
            {running && <Spinner />}
            {running
              ? t.organize.files.scanning
              : location
                ? t.organize.files.scanOne(location === "inbox" ? t.organize.files.inbox : t.organize.files.library)
                : t.organize.files.scanAll}
          </Button>
        </div>

        {scan.result && (
          <div className="flex flex-wrap gap-x-4 gap-y-1 border border-border px-3 py-2 text-[11px]">
            <ScanStat k={t.organize.files.statFound} v={scan.result.found} />
            <ScanStat k={t.organize.files.statNew} v={`+${scan.result.inserted}`} />
            <ScanStat k={t.organize.files.statUpdated} v={scan.result.updated} />
            <ScanStat k={t.organize.files.statUnchanged} v={scan.result.unchanged} />
            <ScanStat k={t.organize.files.statMoved} v={scan.result.moved} />
            <ScanStat k={t.organize.files.statMissing} v={scan.result.missing} />
            <ScanStat k={t.organize.files.statErrors} v={scan.result.errors} danger={scan.result.errors > 0} />
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t.organize.files.searchPlaceholder} className="w-48" />
          {FACET_KEYS.map((key) => (
            <FacetInput
              key={key} facet={key} placeholder={facetPlaceholder[key]} value={tag[key]}
              options={facetOptions(facets, key)}
              onChange={(v) => setTagField(key, v)}
            />
          ))}
          <label className="flex items-center gap-1.5 border border-border px-2 py-1 text-[11px] text-muted">
            <input
              type="checkbox" checked={onlyIssues}
              onChange={(e) => setOnlyIssues(e.target.checked)}
              className="accent-danger"
            />
            {t.organize.files.filterIssues}
          </label>
          {(Object.values(tag).some(Boolean) || onlyIssues) && (
            <button
              onClick={() => { setTag({ genre: "", artist: "", album: "", label: "", ext: "", year: "" }); setOnlyIssues(false); }}
              className="border border-border px-2 py-1 text-[11px] text-muted hover:bg-elevated"
            >{t.organize.files.clearFilters}</button>
          )}
        </div>

        {!loaded ? (
          <Loading />
        ) : rows.length === 0 && !offline ? (
          <EmptyState title={t.organize.files.emptyTitle}>{t.organize.files.emptyBody}</EmptyState>
        ) : (
          <FilesTable rows={rows} sort={sort} dir={dir} onSort={onSort} onEdit={setEditing} />
        )}
      </div>

      {editing && (
        <FileEditPanel
          row={editing}
          facets={facets}
          onClose={() => setEditing(null)}
          onSaved={(updated) => {
            setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
            setEditing(null);
          }}
        />
      )}
    </PageLayout>
  );
}

function Marginalia({ stats }: { stats: LibraryStats | null }) {
  const t = useT();
  if (!stats) return <p className="text-xs text-faint">{t.organize.common.empty}</p>;
  const sev = stats.issues_by_severity;
  const issuesTotal = Object.values(sev).reduce((a, b) => a + b, 0);
  return (
    <div className="flex flex-col gap-4 text-xs">
      <Stat v={stats.files_total} k={t.organize.files.statFiles} />
      <div>
        <Stat v={issuesTotal} k={t.organize.files.statIssues} />
        <div className="mt-1 flex gap-3 text-[11px]">
          <span className="text-danger">{sev.error ?? 0} {t.organize.files.sevErr}</span>
          <span className="text-warning">{sev.warning ?? 0} {t.organize.files.sevWarn}</span>
          <span className="text-muted">{sev.info ?? 0} {t.organize.files.sevInfo}</span>
        </div>
      </div>
      <Stat v={stats.dup_groups} k={t.organize.files.statDups} />
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">{t.organize.files.formats}</div>
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
