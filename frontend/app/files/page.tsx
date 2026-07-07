"use client";

import { useCallback, useEffect, useState } from "react";
import {
  listFiles, libraryStats, listSources, libraryFacets,
  type FileRow, type LibraryStats, type LibraryFacets, type ScanRoot, type FileQuery,
} from "@/lib/api";
import { useJobs } from "@/components/jobs-provider";
import { PageLayout } from "@/components/page-layout";
import { FilesTable } from "@/components/files-table";
import { Alert, EmptyState, Input, Select } from "@/components/ui";

const LIMIT = 500;

// campi tag filtrabili → placeholder mostrato nell'input
const FACETS: [keyof LibraryFacets, string][] = [
  ["genre", "genere…"], ["artist", "artista…"], ["album", "album…"],
  ["label", "label…"], ["ext", "formato…"], ["year", "anno…"],
];

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
  const { scan } = useJobs();
  const [rows, setRows] = useState<FileRow[]>([]);
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
  const setTagField = (k: string, v: string) => setTag((t) => ({ ...t, [k]: v }));

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
      .catch(() => setOffline(true));
    libraryStats().then(setStats).catch(() => setStats(null));
  }, [rootId, onlyIssues, sort, q, tag]);

  useEffect(() => { listSources().then(setRoots).catch(() => {}); }, []);
  useEffect(() => { libraryFacets().then(setFacets).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (scan.status === "done") { load(); libraryFacets().then(setFacets).catch(() => {}); }
  }, [scan.status, load]);

  return (
    <PageLayout
      title="Files"
      meta={stats ? `${rows.length}${stats.files_total > rows.length ? ` di ${stats.files_total}` : ""}` : undefined}
      marginaliaTitle="Libreria"
      marginalia={<Marginalia stats={stats} />}
      guide={<>
        <p>Tutti i file audio trovati nelle radici scansionate.</p>
        <p>Filtra per tag (genere, formato…) o cerca per artista/titolo/path.</p>
        <p>Il conteggio issue segnala i file con problemi sui tag.</p>
      </>}
    >
      <div className="flex flex-col gap-4">
        {offline && <Alert>Backend non raggiungibile. Avvia il server FastAPI.</Alert>}

        <div className="flex flex-wrap items-center gap-2">
          <Select value={rootId} onChange={(e) => setRootId(e.target.value)} className="w-auto">
            <option value="">tutte le radici</option>
            {roots.map((r) => <option key={r.id} value={r.id}>{r.label || r.path}</option>)}
          </Select>
          <Select value={onlyIssues ? "issues" : "all"} onChange={(e) => setOnlyIssues(e.target.value === "issues")} className="w-auto">
            <option value="all">tutti</option>
            <option value="issues">con issue</option>
          </Select>
          <Select value={sort} onChange={(e) => setSort(e.target.value as FileQuery["sort"])} className="w-auto">
            <option value="path">ordina: path</option>
            <option value="artist">ordina: artist</option>
            <option value="title">ordina: title</option>
            <option value="bitrate">ordina: kbps</option>
            <option value="duration">ordina: durata</option>
          </Select>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="cerca…" className="w-48" />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {FACETS.map(([key, ph]) => (
            <FacetInput
              key={key} facet={key} placeholder={ph} value={tag[key]}
              options={facetOptions(facets, key)}
              onChange={(v) => setTagField(key, v)}
            />
          ))}
          {Object.values(tag).some(Boolean) && (
            <button
              onClick={() => setTag({ genre: "", artist: "", album: "", label: "", ext: "", year: "" })}
              className="border border-border px-2 py-1 text-[11px] text-muted hover:bg-elevated"
            >✕ pulisci filtri</button>
          )}
        </div>

        {rows.length === 0 && !offline ? (
          <EmptyState title="Nessun file">Aggiungi una radice in Sources e lancia uno scan.</EmptyState>
        ) : (
          <FilesTable rows={rows} />
        )}
      </div>
    </PageLayout>
  );
}

function Marginalia({ stats }: { stats: LibraryStats | null }) {
  if (!stats) return <p className="text-xs text-faint">—</p>;
  const sev = stats.issues_by_severity;
  const issuesTotal = Object.values(sev).reduce((a, b) => a + b, 0);
  return (
    <div className="flex flex-col gap-4 text-xs">
      <Stat v={stats.files_total} k="file" />
      <div>
        <Stat v={issuesTotal} k="issue" />
        <div className="mt-1 flex gap-3 text-[11px]">
          <span className="text-danger">{sev.error ?? 0} err</span>
          <span className="text-warning">{sev.warning ?? 0} warn</span>
          <span className="text-muted">{sev.info ?? 0} info</span>
        </div>
      </div>
      <Stat v={stats.dup_groups} k="doppioni" />
      <div>
        <div className="mb-1 text-[10px] uppercase tracking-wider text-muted">Formati</div>
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
