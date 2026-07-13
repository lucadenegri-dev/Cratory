"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ClipboardList, Library, Plus, X, ChevronUp, ChevronDown } from "lucide-react";
import { apiGet, createPlaylistFromTracks, errText, importManualPlaylist, trackLabel, type Track } from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Textarea, Field, Checkbox, Badge } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useT } from "@/lib/i18n";

export default function ImportManualPage() {
  const t = useT();
  const router = useRouter();
  const [mode, setMode] = useState<"paste" | "library">("paste");
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Modalità "Dalla libreria": ricerca + selezione multipla
  const [query, setQuery] = useState("");
  const [ownedOnly, setOwnedOnly] = useState(true);
  const [results, setResults] = useState<Track[]>([]);
  const [picked, setPicked] = useState<Track[]>([]);

  useEffect(() => {
    if (mode !== "library") return;
    const timer = setTimeout(() => {
      apiGet<{ total: number; items: Track[] }>("/api/tracks", {
        title: query || undefined,
        has_local_file: ownedOnly ? "true" : undefined,
        limit: 30,
      })
        .then((r) => setResults(r.items))
        .catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(timer);
  }, [mode, query, ownedOnly]);

  const doImport = async () => {
    setError(null);
    setBusy(true);
    try {
      await importManualPlaylist(name.trim() || t.playlists.importManual.defaultPlaylistName, text);
      router.push("/playlists");
    } catch (e) {
      setError(t.playlists.importManual.importFailed(errText(e)));
      setBusy(false);
    }
  };

  const doCreateFromLibrary = async () => {
    setError(null);
    setBusy(true);
    try {
      await createPlaylistFromTracks(name.trim() || t.playlists.importManual.defaultPlaylistName, picked.map((tr) => tr.id));
      router.push("/playlists");
    } catch (e) {
      setError(t.playlists.importManual.createFailed(errText(e)));
      setBusy(false);
    }
  };

  const pick = (tr: Track) => setPicked((p) => (p.some((x) => x.id === tr.id) ? p : [...p, tr]));
  const unpick = (id: number) => setPicked((p) => p.filter((tr) => tr.id !== id));
  const move = (i: number, dir: -1 | 1) =>
    setPicked((p) => {
      const j = i + dir;
      if (j < 0 || j >= p.length) return p;
      const next = [...p];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const lineCount = text.split("\n").filter((l) => l.trim() !== "").length;
  const im = t.playlists.importManual;

  const marginalia = (
    <div className="space-y-4">
      {mode === "paste" ? (
        <div className="space-y-2 text-xs leading-relaxed text-muted">
          <p>{im.oneLinePerTrack}</p>
          <p>{im.formatPrefix} <span className="text-fg">{im.formatArtistTitle}</span> {im.formatOrCsv} <span className="text-fg">{im.formatArtistTitleCsv}</span>.</p>
          <p>{im.noBpmKeyHint}</p>
        </div>
      ) : (
        <div className="space-y-2 text-xs leading-relaxed text-muted">
          <p>{im.libraryHint}</p>
          <p>{im.ownedOnlyFilterHintPrefix} <span className="text-fg">{im.ownedOnlyLabel}</span> {im.ownedOnlyFilterHintSuffix}</p>
        </div>
      )}
      <div className="border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2">
          <span className="text-muted">{mode === "paste" ? im.rowsDetectedLabel : im.tracksSelectedLabel}</span>
          <span className="tnum text-fg">{mode === "paste" ? lineCount : picked.length}</span>
        </div>
      </div>
    </div>
  );

  return (
    <PageLayout title={im.pageTitle} marginaliaTitle={mode === "paste" ? im.formatMarginaliaTitle : im.howItWorksMarginaliaTitle} marginalia={marginalia}>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> {t.playlists.backLink}
      </Link>
      <p className="mb-6 text-sm text-muted">{im.intro}</p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <div className="mb-4 flex gap-2">
        <Button size="sm" variant={mode === "library" ? undefined : "outline"} onClick={() => setMode("library")}>
          <Library size={15} /> {im.fromLibraryButton}
        </Button>
        <Button size="sm" variant={mode === "paste" ? undefined : "outline"} onClick={() => setMode("paste")}>
          <ClipboardList size={15} /> {im.pasteTracklistButton}
        </Button>
      </div>

      <Card>
        <CardHeader
          title={mode === "paste" ? im.tracklistCardTitle : im.fromLibraryCardTitle}
          subtitle={mode === "paste"
            ? im.noBpmKeyHint
            : im.searchSelectOrderSubtitle}
        />
        <div className="grid gap-3 p-4">
          <Field label={im.playlistNameLabel}>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={im.playlistNamePlaceholder}
              disabled={busy}
            />
          </Field>

          {mode === "paste" ? (
            <>
              <Field label={im.tracksFieldLabel}>
                <Textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={10}
                  placeholder={im.tracklistPlaceholderExample}
                  disabled={busy}
                />
              </Field>
              <div className="flex justify-end">
                <Button onClick={doImport} disabled={busy || text.trim() === ""}>
                  {busy ? <Spinner /> : <ClipboardList size={15} />} {im.importTracklistButton}
                </Button>
              </div>
            </>
          ) : (
            <>
              <div className="flex items-center gap-3">
                <Input
                  className="h-9 flex-1"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={im.searchByTitlePlaceholder}
                  disabled={busy}
                />
                <Checkbox label={im.ownedOnlyLabel} checked={ownedOnly} onChange={setOwnedOnly} />
              </div>

              <div className="max-h-64 divide-y divide-border overflow-y-auto border border-border">
                {results.map((tr) => (
                  <button
                    key={tr.id}
                    type="button"
                    onClick={() => pick(tr)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-elevated"
                  >
                    <Plus size={14} className="shrink-0 text-muted" />
                    <span className="min-w-0 flex-1 truncate">{trackLabel(tr)}</span>
                    {tr.has_local_file && <Badge tone="success">FILE</Badge>}
                  </button>
                ))}
                {results.length === 0 && (
                  <div className="px-3 py-6 text-center text-sm text-muted">{im.noResults}</div>
                )}
              </div>

              {picked.length > 0 && (
                <Field label={im.playlistFieldLabel(picked.length)}>
                  <ol className="divide-y divide-border border border-border">
                    {picked.map((tr, i) => (
                      <li key={tr.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                        <span className="tnum w-6 shrink-0 text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
                        <span className="min-w-0 flex-1 truncate">{trackLabel(tr)}</span>
                        <button type="button" onClick={() => move(i, -1)} aria-label={im.moveUpAria} className="text-muted hover:text-fg"><ChevronUp size={14} /></button>
                        <button type="button" onClick={() => move(i, 1)} aria-label={im.moveDownAria} className="text-muted hover:text-fg"><ChevronDown size={14} /></button>
                        <button type="button" onClick={() => unpick(tr.id)} aria-label={im.removeAria} className="text-muted hover:text-fg"><X size={14} /></button>
                      </li>
                    ))}
                  </ol>
                </Field>
              )}

              <div className="flex justify-end">
                <Button onClick={doCreateFromLibrary} disabled={busy || picked.length === 0}>
                  {busy ? <Spinner /> : <Library size={15} />} {im.createPlaylistButton(picked.length)}
                </Button>
              </div>
            </>
          )}
        </div>
      </Card>
    </PageLayout>
  );
}
