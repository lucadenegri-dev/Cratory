"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, Search } from "lucide-react";
import {
  previewLikedTracks,
  importSelectedLikedTracks,
  fmtDuration,
  type LikedTrackPreview,
} from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { useT } from "@/lib/i18n";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ImportLikedPage() {
  const t = useT();
  const router = useRouter();
  const jobs = useJobs();
  const [preview, setPreview] = useState<LikedTrackPreview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    previewLikedTracks()
      .then(setPreview)
      .catch((e) => setError(err(e)));
  }, []);

  const alreadyCount = useMemo(
    () => (preview ?? []).filter((tr) => tr.already_imported).length,
    [preview],
  );

  const filtered = useMemo(() => {
    const rows = preview ?? [];
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter(
      (tr) =>
        (tr.title ?? "").toLowerCase().includes(needle) ||
        (tr.artist ?? "").toLowerCase().includes(needle),
    );
  }, [preview, q]);

  const toggle = (id: string) =>
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const selectVisible = () =>
    setSelected((cur) => {
      const next = new Set(cur);
      for (const tr of filtered) if (!tr.already_imported) next.add(tr.spotify_id);
      return next;
    });

  const clearSelection = () => setSelected(new Set());

  const liked = t.playlists.importSpotify.liked;

  const doImport = async () => {
    setError(null);
    setImporting(true);
    try {
      await importSelectedLikedTracks([...selected]);
      jobs.refresh();
      router.push("/playlists");
    } catch (e) {
      setError(liked.importFailed(err(e)));
      setImporting(false);
    }
  };

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>{liked.noteCuratedPrefix} <span className="text-fg">{liked.noteCuratedTerm}</span> {liked.noteCuratedSuffix}</p>
      <p>{liked.noteAdditive}</p>
    </div>
  );

  return (
    <PageLayout title={liked.pageTitle} marginaliaTitle={t.playlists.marginaliaNotes} marginalia={marginalia}>
      <Link href="/playlists/import-spotify" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> {liked.backLink}
      </Link>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {!preview && !error && <Loading />}

      {preview && (
        <Card>
          <CardHeader
            title={liked.cardTitle}
            subtitle={liked.cardSubtitle(preview.length, alreadyCount, selected.size)}
            action={
              <Button size="sm" onClick={doImport} disabled={selected.size === 0 || importing}>
                {importing ? <Spinner /> : <Download size={15} />} {liked.importSelectedButton(selected.size)}
              </Button>
            }
          />
          <div className="px-5 py-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <div className="relative min-w-0 flex-1">
                <Search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                <Input
                  className="h-9 pl-8"
                  placeholder={liked.filterPlaceholder}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
              <Button size="sm" variant="outline" onClick={selectVisible}>{liked.selectVisibleButton}</Button>
              <Button size="sm" variant="ghost" onClick={clearSelection} disabled={selected.size === 0}>{liked.deselectButton}</Button>
            </div>

            {preview.length === 0 && <p className="text-sm text-muted">{liked.noSavedTracks}</p>}
            {preview.length > 0 && filtered.length === 0 && <p className="text-sm text-muted">{liked.noMatchFilter}</p>}

            <div className="max-h-[32rem] overflow-y-auto">
              <div className="grid gap-1">
                {filtered.map((tr) => {
                  const checked = tr.already_imported || selected.has(tr.spotify_id);
                  return (
                    <label
                      key={tr.spotify_id}
                      className={`flex items-center gap-3 border border-border px-3 py-2 ${tr.already_imported ? "opacity-50" : "cursor-pointer hover:bg-elevated/40"}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={tr.already_imported}
                        onChange={() => toggle(tr.spotify_id)}
                        className="h-4 w-4 shrink-0 accent-[var(--color-fg)]"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{tr.title ?? <span className="italic text-faint">{t.library.untitledTrack}</span>}</div>
                        <div className="truncate text-xs text-faint">{tr.artist ?? "—"}</div>
                      </div>
                      <span className="tnum shrink-0 text-xs text-muted">{fmtDuration(tr.duration_seconds)}</span>
                    </label>
                  );
                })}
              </div>
            </div>
          </div>
        </Card>
      )}
    </PageLayout>
  );
}
