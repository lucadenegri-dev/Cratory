"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ClipboardList, Library, ListPlus } from "lucide-react";
import { apiGet, addTracksToPlaylist, createPlaylistFromTracks, errText, importManualPlaylist, listImportedPlaylists, trackLabel, type Playlist, type Track } from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Textarea, Field, Checkbox, Badge, Select } from "@/components/ui";
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

  // Modalità "Dalla libreria": filtri + selezione multipla a checkbox
  const [query, setQuery] = useState("");
  const [ownedOnly, setOwnedOnly] = useState(true);
  const [genre, setGenre] = useState("");
  const [inPlaylist, setInPlaylist] = useState("");   // id playlist come stringa; "" = tutte
  const [results, setResults] = useState<Track[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [manualPlaylists, setManualPlaylists] = useState<Playlist[]>([]);
  const [addTarget, setAddTarget] = useState("");     // id playlist per "aggiungi a esistente"
  const [feedback, setFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (mode !== "library") return;
    listImportedPlaylists()
      .then((all) => setManualPlaylists(all.filter((p) => p.kind === "manual")))
      .catch(() => setManualPlaylists([]));
  }, [mode]);

  useEffect(() => {
    if (mode !== "library") return;
    const timer = setTimeout(() => {
      apiGet<{ total: number; items: Track[] }>("/api/tracks", {
        title: query || undefined,
        genre: genre || undefined,
        has_local_file: ownedOnly ? "true" : undefined,
        in_playlist: inPlaylist || undefined,
        limit: 50,
      })
        .then((r) => { setResults(r.items); setTotal(r.total); })
        .catch(() => { setResults([]); setTotal(0); });
    }, 300);
    return () => clearTimeout(timer);
  }, [mode, query, genre, ownedOnly, inPlaylist]);

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
      await createPlaylistFromTracks(name.trim() || t.playlists.importManual.defaultPlaylistName, [...selected]);
      router.push("/playlists");
    } catch (e) {
      setError(t.playlists.importManual.createFailed(errText(e)));
      setBusy(false);
    }
  };

  const doAddToExisting = async () => {
    if (!addTarget) return;
    setError(null);
    setFeedback(null);
    setBusy(true);
    try {
      const res = await addTracksToPlaylist(Number(addTarget), [...selected]);
      setFeedback(t.playlists.importManual.addedFeedback(res.added, res.skipped));
      setBusy(false);
    } catch (e) {
      setError(t.playlists.importManual.addFailed(errText(e)));
      setBusy(false);
    }
  };

  const toggle = (id: number) =>
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });

  const selectAllMatching = async () => {
    try {
      const r = await apiGet<{ total: number; items: Track[] }>("/api/tracks", {
        title: query || undefined,
        genre: genre || undefined,
        has_local_file: ownedOnly ? "true" : undefined,
        in_playlist: inPlaylist || undefined,
        limit: 0,
      });
      setSelected(new Set(r.items.map((tr) => tr.id)));
    } catch {
      /* noop: la selezione resta invariata */
    }
  };

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
          <span className="tnum text-fg">{mode === "paste" ? lineCount : selected.size}</span>
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
            : im.filterSelectSubtitle}
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
              {feedback && <Alert tone="success">{feedback}</Alert>}

              <div className="grid gap-2 sm:grid-cols-2">
                <Input
                  className="h-9"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder={im.searchByTitlePlaceholder}
                  disabled={busy}
                />
                <Input
                  className="h-9"
                  value={genre}
                  onChange={(e) => setGenre(e.target.value)}
                  placeholder={im.genreFilterPlaceholder}
                  disabled={busy}
                />
                <Select
                  className="h-9"
                  value={inPlaylist}
                  onChange={(e) => setInPlaylist(e.target.value)}
                  disabled={busy}
                >
                  <option value="">{im.playlistFilterAllOption}</option>
                  {manualPlaylists.map((p) => (
                    <option key={p.id} value={String(p.id)}>{p.name}</option>
                  ))}
                </Select>
                <div className="flex items-center">
                  <Checkbox label={im.ownedOnlyLabel} checked={ownedOnly} onChange={setOwnedOnly} />
                </div>
              </div>

              <div className="flex items-center justify-between gap-2 text-xs text-muted">
                <span>{im.selectedCount(selected.size)}</span>
                <div className="flex gap-3">
                  <button type="button" onClick={selectAllMatching} className="hover:text-fg" disabled={total === 0}>
                    {im.selectAllMatching(total)}
                  </button>
                  <button type="button" onClick={() => setSelected(new Set())} className="hover:text-fg" disabled={selected.size === 0}>
                    {im.clearSelection}
                  </button>
                </div>
              </div>

              <div className="max-h-72 divide-y divide-border overflow-y-auto border border-border">
                {results.map((tr) => (
                  <label
                    key={tr.id}
                    className="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-sm transition-colors hover:bg-elevated"
                  >
                    <input
                      type="checkbox"
                      checked={selected.has(tr.id)}
                      onChange={() => toggle(tr.id)}
                      className="shrink-0"
                    />
                    <span className="min-w-0 flex-1 truncate">{trackLabel(tr)}</span>
                    {tr.has_local_file && <Badge tone="success">FILE</Badge>}
                  </label>
                ))}
                {results.length === 0 && (
                  <div className="px-3 py-6 text-center text-sm text-muted">{im.noResults}</div>
                )}
              </div>

              <div className="flex flex-wrap items-end justify-between gap-3 border-t border-border pt-3">
                <div className="flex items-end gap-2">
                  <Select
                    className="h-9"
                    value={addTarget}
                    onChange={(e) => setAddTarget(e.target.value)}
                    disabled={busy}
                    aria-label={im.addToExistingLabel}
                  >
                    <option value="">{im.addToExistingPlaceholder}</option>
                    {manualPlaylists.map((p) => (
                      <option key={p.id} value={String(p.id)}>{p.name}</option>
                    ))}
                  </Select>
                  <Button variant="outline" onClick={doAddToExisting} disabled={busy || selected.size === 0 || !addTarget}>
                    {busy ? <Spinner /> : <ListPlus size={15} />} {im.addToExistingButton}
                  </Button>
                </div>
                <Button onClick={doCreateFromLibrary} disabled={busy || selected.size === 0}>
                  {busy ? <Spinner /> : <Library size={15} />} {im.createPlaylistButton(selected.size)}
                </Button>
              </div>
            </>
          )}
        </div>
      </Card>
    </PageLayout>
  );
}
