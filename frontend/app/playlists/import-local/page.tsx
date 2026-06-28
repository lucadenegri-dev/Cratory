"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowUp, Folder, HardDriveDownload } from "lucide-react";
import {
  browseLocalFolder,
  startLocalImport,
  localImportStatus,
  type LocalBrowseResponse,
  type LocalImportJobStatus,
} from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Field } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ImportLocalPage() {
  const router = useRouter();
  const [view, setView] = useState<LocalBrowseResponse | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [job, setJob] = useState<LocalImportJobStatus | null>(null);
  const nameEdited = useRef(false);

  const load = useCallback((path?: string) => {
    browseLocalFolder(path)
      .then((res) => {
        setError(null);
        setView(res);
        if (!nameEdited.current) {
          const segs = res.current_path.split(/[\\/]/).filter(Boolean);
          setName(segs[segs.length - 1] ?? "");
        }
      })
      .catch((e) => setError(`Navigazione fallita: ${err(e)}`));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Polling dello stato mentre il job è in corso.
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const id = setInterval(() => {
      localImportStatus()
        .then((st) => {
          setJob(st);
          if (st.status === "done" && st.playlist_id) {
            clearInterval(id);
            router.push(`/playlists/${st.playlist_id}`);
          } else if (st.status === "done" && !st.playlist_id) {
            clearInterval(id);
            setError("Import completato ma nessuna playlist creata.");
          }
        })
        .catch(() => {
          /* ritenta al prossimo tick */
        });
    }, 1000);
    return () => clearInterval(id);
  }, [job, router]);

  const doImport = () => {
    if (!view) return;
    setError(null);
    startLocalImport(view.current_path, name.trim() || undefined)
      .then((st) => setJob(st))
      .catch((e) => setError(`Import fallito: ${err(e)}`));
  };

  const running = job?.status === "running";

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>Scegli una cartella: i file audio (anche nelle sottocartelle) entrano in una sola playlist.</p>
      <p>Si leggono solo i <span className="text-fg">tag</span>: l&apos;audio non viene copiato.</p>
      <p>BPM/key arrivano dopo, dall&apos;arricchimento automatico.</p>
    </div>
  );

  return (
    <PageLayout title="Import — Cartella locale" marginaliaTitle="Come funziona" marginalia={marginalia}>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Playlist
      </Link>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {job && (
        <div className="mb-4" role="status" aria-live="polite">
          <Alert tone={job.status === "error" ? "danger" : job.status === "done" ? "success" : "info"}>
            {job.status === "running" && <>Import in corso… {job.processed}/{job.total} file</>}
            {job.status === "done" && <>Completato: {job.created} nuove, {job.updated} aggiornate{job.failed ? `, ${job.failed} saltate` : ""}.</>}
            {job.status === "error" && <>Errore: {job.error}</>}
          </Alert>
        </div>
      )}

      <Card>
        <CardHeader title="Scegli la cartella" subtitle={view?.current_path ?? "Caricamento…"} />
        <div className="grid gap-3 p-4">
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={!view?.parent_path || running}
              onClick={() => view?.parent_path && load(view.parent_path)}
            >
              <ArrowUp size={15} /> Su
            </Button>
            {view?.dirs.map((d) => (
              <Button key={d.path} size="sm" variant="outline" disabled={running} onClick={() => load(d.path)}>
                <Folder size={15} /> {d.name}
                {d.audio_file_count > 0 && <span className="ml-1 text-muted tnum">({d.audio_file_count})</span>}
              </Button>
            ))}
            {view && view.dirs.length === 0 && <span className="text-sm text-muted">Nessuna sottocartella.</span>}
          </div>

          <Field label="Nome playlist">
            <Input value={name} onChange={(e) => { nameEdited.current = true; setName(e.target.value); }} disabled={running} placeholder="Nome della playlist" />
          </Field>

          <div className="flex justify-end">
            <Button onClick={doImport} disabled={!view || running}>
              {running ? <Spinner /> : <HardDriveDownload size={15} />} Importa questa cartella
            </Button>
          </div>
        </div>
      </Card>
    </PageLayout>
  );
}
