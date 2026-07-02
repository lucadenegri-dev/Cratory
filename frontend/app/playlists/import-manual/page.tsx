"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ClipboardList, Library, Plus, X, ChevronUp, ChevronDown } from "lucide-react";
import { apiGet, createPlaylistFromTracks, importManualPlaylist, trackLabel, type Track } from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Textarea, Field, Checkbox, Badge } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ImportManualPage() {
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
    const t = setTimeout(() => {
      apiGet<{ total: number; items: Track[] }>("/api/tracks", {
        title: query || undefined,
        has_local_file: ownedOnly ? "true" : undefined,
        limit: 30,
      })
        .then((r) => setResults(r.items))
        .catch(() => setResults([]));
    }, 300);
    return () => clearTimeout(t);
  }, [mode, query, ownedOnly]);

  const doImport = async () => {
    setError(null);
    setBusy(true);
    try {
      await importManualPlaylist(name.trim() || "Playlist manuale", text);
      router.push("/playlists");
    } catch (e) {
      setError(`Import manuale fallito: ${err(e)}`);
      setBusy(false);
    }
  };

  const doCreateFromLibrary = async () => {
    setError(null);
    setBusy(true);
    try {
      await createPlaylistFromTracks(name.trim() || "Playlist manuale", picked.map((t) => t.id));
      router.push("/playlists");
    } catch (e) {
      setError(`Creazione fallita: ${err(e)}`);
      setBusy(false);
    }
  };

  const pick = (t: Track) => setPicked((p) => (p.some((x) => x.id === t.id) ? p : [...p, t]));
  const unpick = (id: number) => setPicked((p) => p.filter((t) => t.id !== id));
  const move = (i: number, dir: -1 | 1) =>
    setPicked((p) => {
      const j = i + dir;
      if (j < 0 || j >= p.length) return p;
      const next = [...p];
      [next[i], next[j]] = [next[j], next[i]];
      return next;
    });

  const lineCount = text.split("\n").filter((l) => l.trim() !== "").length;

  const marginalia = (
    <div className="space-y-4">
      {mode === "paste" ? (
        <div className="space-y-2 text-xs leading-relaxed text-muted">
          <p>Una riga per traccia.</p>
          <p>Formato <span className="text-fg">Artista - Titolo</span> oppure CSV <span className="text-fg">artista,titolo</span>.</p>
          <p>Le tracce entrano senza BPM/key: l&apos;arricchimento parte da solo dopo l&apos;import.</p>
        </div>
      ) : (
        <div className="space-y-2 text-xs leading-relaxed text-muted">
          <p>Cerca tra le tracce già in libreria e componi la playlist nell&apos;ordine che vuoi.</p>
          <p>Il filtro <span className="text-fg">solo possedute</span> limita ai file su disco.</p>
        </div>
      )}
      <div className="border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2">
          <span className="text-muted">{mode === "paste" ? "Righe rilevate" : "Tracce selezionate"}</span>
          <span className="tnum text-fg">{mode === "paste" ? lineCount : picked.length}</span>
        </div>
      </div>
    </div>
  );

  return (
    <PageLayout title="Nuova playlist" marginaliaTitle={mode === "paste" ? "Formato" : "Come funziona"} marginalia={marginalia}>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Playlist
      </Link>
      <p className="mb-6 text-sm text-muted">Componi una playlist dalla libreria oppure incolla una tracklist trovata sul web.</p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <div className="mb-4 flex gap-2">
        <Button size="sm" variant={mode === "library" ? undefined : "outline"} onClick={() => setMode("library")}>
          <Library size={15} /> Dalla libreria
        </Button>
        <Button size="sm" variant={mode === "paste" ? undefined : "outline"} onClick={() => setMode("paste")}>
          <ClipboardList size={15} /> Incolla tracklist
        </Button>
      </div>

      <Card>
        <CardHeader
          title={mode === "paste" ? "Tracklist" : "Dalla libreria"}
          subtitle={mode === "paste"
            ? "Le tracce entrano senza BPM/key: l'arricchimento parte da solo dopo l'import."
            : "Cerca, seleziona e ordina le tracce della playlist."}
        />
        <div className="grid gap-3 p-4">
          <Field label="Nome playlist">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Es. Crate digging giugno"
              disabled={busy}
            />
          </Field>

          {mode === "paste" ? (
            <>
              <Field label="Tracce">
                <Textarea
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  rows={10}
                  placeholder={"Daft Punk - Da Funk\nBonobo - Kerala\nFour Tet - Baby"}
                  disabled={busy}
                />
              </Field>
              <div className="flex justify-end">
                <Button onClick={doImport} disabled={busy || text.trim() === ""}>
                  {busy ? <Spinner /> : <ClipboardList size={15} />} Importa tracklist
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
                  placeholder="Cerca per titolo…"
                  disabled={busy}
                />
                <Checkbox label="solo possedute" checked={ownedOnly} onChange={setOwnedOnly} />
              </div>

              <div className="max-h-64 divide-y divide-border overflow-y-auto border border-border">
                {results.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    onClick={() => pick(t)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-elevated"
                  >
                    <Plus size={14} className="shrink-0 text-muted" />
                    <span className="min-w-0 flex-1 truncate">{trackLabel(t)}</span>
                    {t.has_local_file && <Badge tone="success">FILE</Badge>}
                  </button>
                ))}
                {results.length === 0 && (
                  <div className="px-3 py-6 text-center text-sm text-muted">Nessun risultato.</div>
                )}
              </div>

              {picked.length > 0 && (
                <Field label={`Playlist (${picked.length})`}>
                  <ol className="divide-y divide-border border border-border">
                    {picked.map((t, i) => (
                      <li key={t.id} className="flex items-center gap-2 px-3 py-2 text-sm">
                        <span className="tnum w-6 shrink-0 text-xs text-faint">{String(i + 1).padStart(2, "0")}</span>
                        <span className="min-w-0 flex-1 truncate">{trackLabel(t)}</span>
                        <button type="button" onClick={() => move(i, -1)} aria-label="Su" className="text-muted hover:text-fg"><ChevronUp size={14} /></button>
                        <button type="button" onClick={() => move(i, 1)} aria-label="Giù" className="text-muted hover:text-fg"><ChevronDown size={14} /></button>
                        <button type="button" onClick={() => unpick(t.id)} aria-label="Rimuovi" className="text-muted hover:text-fg"><X size={14} /></button>
                      </li>
                    ))}
                  </ol>
                </Field>
              )}

              <div className="flex justify-end">
                <Button onClick={doCreateFromLibrary} disabled={busy || picked.length === 0}>
                  {busy ? <Spinner /> : <Library size={15} />} Crea playlist ({picked.length})
                </Button>
              </div>
            </>
          )}
        </div>
      </Card>
    </PageLayout>
  );
}
