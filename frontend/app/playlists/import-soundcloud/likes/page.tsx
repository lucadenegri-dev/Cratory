"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, Search } from "lucide-react";
import {
  previewSoundcloudLikes,
  importSelectedSoundcloudLikes,
  fmtDuration,
  type SoundCloudLikedTrackPreview,
} from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ImportSoundcloudLikesPage() {
  const router = useRouter();
  const [preview, setPreview] = useState<SoundCloudLikedTrackPreview[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [importing, setImporting] = useState(false);

  useEffect(() => {
    previewSoundcloudLikes()
      .then(setPreview)
      .catch((e) => setError(err(e)));
  }, []);

  const alreadyCount = useMemo(
    () => (preview ?? []).filter((t) => t.already_imported).length,
    [preview],
  );

  const filtered = useMemo(() => {
    const rows = preview ?? [];
    const needle = q.trim().toLowerCase();
    if (!needle) return rows;
    return rows.filter(
      (t) =>
        (t.title ?? "").toLowerCase().includes(needle) ||
        (t.artist ?? "").toLowerCase().includes(needle),
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
      for (const t of filtered) if (!t.already_imported) next.add(t.track_id);
      return next;
    });

  const doImport = async () => {
    setError(null);
    setImporting(true);
    try {
      await importSelectedSoundcloudLikes([...selected]);
      router.push("/playlists");
    } catch (e) {
      setError(`Import fallito: ${err(e)}`);
      setImporting(false);
    }
  };

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>La playlist <span className="text-fg">SoundCloud Likes</span> cresce solo con i brani che selezioni. L&apos;import è additivo.</p>
      <p>Vengono mostrati gli ultimi 100 like: quelli già importati appaiono spuntati e disabilitati.</p>
    </div>
  );

  return (
    <PageLayout title="Import — Like SoundCloud" marginaliaTitle="Note" marginalia={marginalia}>
      <Link href="/playlists/import-soundcloud" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Import SoundCloud
      </Link>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {!preview && !error && <Loading />}

      {preview && (
        <Card>
          <CardHeader
            title="I tuoi like recenti"
            subtitle={`${preview.length} like · ${alreadyCount} già importati · ${selected.size} selezionati`}
            action={
              <Button size="sm" onClick={doImport} disabled={selected.size === 0 || importing}>
                {importing ? <Spinner /> : <Download size={15} />} Importa selezionati ({selected.size})
              </Button>
            }
          />
          <div className="px-5 py-4">
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <div className="relative min-w-0 flex-1">
                <Search size={15} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
                <Input
                  className="h-9 pl-8"
                  placeholder="Filtra per artista o titolo"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                />
              </div>
              <Button size="sm" variant="outline" onClick={selectVisible}>Seleziona visibili</Button>
              <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())} disabled={selected.size === 0}>Deseleziona</Button>
            </div>

            {preview.length === 0 && <p className="text-sm text-muted">Nessun like trovato.</p>}
            {preview.length > 0 && filtered.length === 0 && <p className="text-sm text-muted">Nessun brano con questo filtro.</p>}

            <div className="max-h-[32rem] overflow-y-auto">
              <div className="grid gap-1">
                {filtered.map((t) => {
                  const checked = t.already_imported || selected.has(t.track_id);
                  return (
                    <label
                      key={t.track_id}
                      className={`flex items-center gap-3 border border-border px-3 py-2 ${t.already_imported ? "opacity-50" : "cursor-pointer hover:bg-elevated/40"}`}
                    >
                      <input
                        type="checkbox"
                        checked={checked}
                        disabled={t.already_imported}
                        onChange={() => toggle(t.track_id)}
                        className="h-4 w-4 shrink-0 accent-[var(--color-fg)]"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-sm font-medium">{t.title ?? <span className="italic text-faint">senza titolo</span>}</div>
                        <div className="truncate text-xs text-faint">{t.artist ?? "—"}</div>
                      </div>
                      <span className="tnum shrink-0 text-xs text-muted">{fmtDuration(t.duration_seconds)}</span>
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
