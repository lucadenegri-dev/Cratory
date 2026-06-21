"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, ClipboardList } from "lucide-react";
import { importManualPlaylist } from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Textarea, Field } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ImportManualPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

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

  const lineCount = text.split("\n").filter((l) => l.trim() !== "").length;

  const marginalia = (
    <div className="space-y-4">
      <div className="space-y-2 text-xs leading-relaxed text-muted">
        <p>Una riga per traccia.</p>
        <p>Formato <span className="text-fg">Artista - Titolo</span> oppure CSV <span className="text-fg">artista,titolo</span>.</p>
        <p>Le tracce entrano senza BPM/key: l&apos;arricchimento parte da solo dopo l&apos;import.</p>
      </div>
      <div className="border-t border-border pt-4 text-xs">
        <div className="flex justify-between gap-2"><span className="text-muted">Righe rilevate</span><span className="tnum text-fg">{lineCount}</span></div>
      </div>
    </div>
  );

  return (
    <PageLayout title="Import — Manuale" marginaliaTitle="Formato" marginalia={marginalia}>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Playlist
      </Link>
      <p className="mb-6 text-sm text-muted">Incolla una tracklist: una riga per traccia, formato “Artista - Titolo” (o CSV “artista,titolo”).</p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      <Card>
        <CardHeader title="Tracklist" subtitle="Le tracce entrano senza BPM/key: l'arricchimento parte da solo dopo l'import." />
        <div className="grid gap-3 p-4">
          <Field label="Nome playlist">
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Es. Crate digging giugno"
              disabled={busy}
            />
          </Field>
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
        </div>
      </Card>
    </PageLayout>
  );
}
