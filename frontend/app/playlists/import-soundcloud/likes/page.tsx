"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, Search } from "lucide-react";
import {
  previewSoundcloudLikes,
  importSelectedSoundcloudLikes,
  errText,
  fmtDuration,
  type SoundCloudLikedTrackPreview,
} from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { useT } from "@/lib/i18n";

export default function ImportSoundcloudLikesPage() {
  const t = useT();
  const router = useRouter();
  const jobs = useJobs();
  const [preview, setPreview] = useState<SoundCloudLikedTrackPreview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    previewSoundcloudLikes()
      .then(setPreview)
      .catch((e) => setError(errText(e)));
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
        (tr.uploader ?? "").toLowerCase().includes(needle),
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
      for (const tr of filtered) if (!tr.already_imported) next.add(tr.track_id);
      return next;
    });

  const likes = t.playlists.importSoundcloud.likes;

  const doImport = async () => {
    setError(null);
    setImporting(true);
    try {
      await importSelectedSoundcloudLikes([...selected]);
      jobs.refresh();
      router.push("/playlists");
    } catch (e) {
      setError(likes.importFailed(errText(e)));
      setImporting(false);
    }
  };

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>{likes.noteCuratedPrefix} <span className="text-fg">{likes.noteCuratedTerm}</span> {likes.noteCuratedSuffix}</p>
      <p>{likes.noteRecent}</p>
      <p>{likes.noteImportEnrich}</p>
    </div>
  );

  return (
    <PageLayout title={likes.pageTitle} marginaliaTitle={t.playlists.marginaliaNotes} marginalia={marginalia}>
      <Link href="/playlists/import-soundcloud" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> {likes.backLink}
      </Link>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {!preview && !error && <Loading />}

      {preview && (
        <Card>
          <CardHeader
            title={likes.cardTitle}
            subtitle={likes.cardSubtitle(preview.length, alreadyCount, selected.size)}
            action={
              <Button size="sm" onClick={doImport} disabled={selected.size === 0 || importing}>
                {importing ? <Spinner /> : <Download size={15} />} {likes.importSelectedButton(selected.size)}
              </Button>
            }
          />
          <div className="px-5 py-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <div className="relative min-w-0 flex-1">
                <Search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                <Input
                  className="h-9 pl-8"
                  placeholder={likes.filterPlaceholder}
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
              <Button size="sm" variant="outline" onClick={selectVisible}>{likes.selectVisibleButton}</Button>
              <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())} disabled={selected.size === 0}>{likes.deselectButton}</Button>
            </div>

            {preview.length === 0 && <p className="text-sm text-muted">{likes.noLikesFound}</p>}
            {preview.length > 0 && filtered.length === 0 && <p className="text-sm text-muted">{likes.noMatchFilter}</p>}

            <div className="max-h-[32rem] overflow-y-auto">
              <div className="grid gap-1">
                {filtered.map((tr) => {
                  const checked = tr.already_imported || selected.has(tr.track_id);
                  return (
                    <label
                      key={tr.track_id}
                      className={`flex items-center gap-3 border border-border px-3 py-2 ${tr.already_imported ? "opacity-50" : "cursor-pointer hover:bg-elevated/40"}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={tr.already_imported}
                        onChange={() => toggle(tr.track_id)}
                        className="h-4 w-4 shrink-0 accent-[var(--color-fg)]"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{tr.title ?? <span className="italic text-faint">{t.library.untitledTrack}</span>}</div>
                        <div className="truncate text-xs text-faint">{tr.uploader ?? "—"}</div>
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
