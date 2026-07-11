"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, Heart, Settings } from "lucide-react";
import { importSoundcloudPlaylist, soundcloudStatus, type SoundCloudStatus } from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Field } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ImportSoundcloudPage() {
  const router = useRouter();
  const [status, setStatus] = useState<SoundCloudStatus | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    soundcloudStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const doImport = async () => {
    setError(null);
    setBusy(true);
    try {
      await importSoundcloudPlaylist(url.trim());
      router.push("/playlists");
    } catch (e) {
      setError(`Import fallito: ${err(e)}`);
      setBusy(false);
    }
  };

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>Solo metadati: titolo, artista, durata, link. Nessun audio, mai.</p>
      <p>Per una playlist privata incolla il <span className="text-fg">secret link</span> (Share → Copy link).</p>
      <p>Su SoundCloud l&apos;artista è spesso l&apos;uploader: i titoli &quot;Artista - Titolo&quot; vengono separati in automatico.</p>
    </div>
  );

  return (
    <PageLayout title="Import — SoundCloud" marginaliaTitle="Note" marginalia={marginalia}>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> Playlist
      </Link>
      <p className="mb-6 text-sm text-muted">
        Incolla l&apos;URL di una playlist SoundCloud: le tracce entrano come lead,
        da arricchire, scaricare e organizzare.
      </p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {status && !status.available && (
        <div className="mb-6">
          <Alert tone="warning">yt-dlp non disponibile nel backend: l&apos;import non funzionerà.</Alert>
        </div>
      )}

      <div className="grid gap-4">
        <Card>
          <CardHeader title="Playlist da URL" subtitle="Pubblica o secret link" />
          <div className="grid gap-3 p-4">
            <Field label="URL playlist">
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://soundcloud.com/utente/sets/nome-playlist"
                disabled={busy}
              />
            </Field>
            <div className="flex justify-end">
              <Button onClick={doImport} disabled={busy || url.trim() === ""}>
                {busy ? <Spinner /> : <Download size={15} />} Importa playlist
              </Button>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title="I miei like"
            subtitle={status?.username
              ? `Like recenti di ${status.username}, con selezione`
              : "Configura lo username SoundCloud in Impostazioni"}
            action={status?.username ? (
              <Button size="sm" variant="outline" onClick={() => router.push("/playlists/import-soundcloud/likes")}>
                <Heart size={15} /> Apri
              </Button>
            ) : (
              <Button size="sm" variant="outline" onClick={() => router.push("/settings")}>
                <Settings size={15} /> Impostazioni
              </Button>
            )}
          />
        </Card>
      </div>
    </PageLayout>
  );
}
