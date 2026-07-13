"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowLeft, Download, Heart, Settings } from "lucide-react";
import { errText, importSoundcloudPlaylist, soundcloudStatus, type SoundCloudStatus } from "@/lib/api";
import { Card, CardHeader, Button, Alert, Spinner, Input, Field } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { useJobs } from "@/components/jobs-provider";
import { useT } from "@/lib/i18n";

export default function ImportSoundcloudPage() {
  const t = useT();
  const router = useRouter();
  const jobs = useJobs();
  const [status, setStatus] = useState<SoundCloudStatus | null>(null);
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    soundcloudStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const isc = t.playlists.importSoundcloud;

  const doImport = async () => {
    setError(null);
    setBusy(true);
    try {
      await importSoundcloudPlaylist(url.trim());
      jobs.refresh();
      router.push("/playlists");
    } catch (e) {
      setError(isc.importFailed(errText(e)));
      setBusy(false);
    }
  };

  const marginalia = (
    <div className="space-y-2 text-xs leading-relaxed text-muted">
      <p>{isc.noteMetadataOnly}</p>
      <p>{isc.notePrivateHintPrefix} <span className="text-fg">{isc.notePrivateHintTerm}</span> {isc.notePrivateHintSuffix}</p>
      <p>{isc.noteUploaderHintPrefix} {isc.noteUploaderHintTerm} {isc.noteUploaderHintSuffix}</p>
    </div>
  );

  return (
    <PageLayout title={isc.pageTitle} marginaliaTitle={t.playlists.marginaliaNotes} marginalia={marginalia}>
      <Link href="/playlists" className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> {t.playlists.backLink}
      </Link>
      <p className="mb-6 text-sm text-muted">
        {isc.intro}
      </p>

      {error && <div className="mb-4"><Alert tone="danger">⚠ {error}</Alert></div>}

      {status && !status.available && (
        <div className="mb-6">
          <Alert tone="warning">{isc.ytdlpWarning}</Alert>
        </div>
      )}

      <div className="grid gap-4">
        <Card>
          <CardHeader title={isc.urlCardTitle} subtitle={isc.urlCardSubtitle} />
          <div className="grid gap-3 p-4">
            <Field label={isc.urlFieldLabel}>
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder={isc.urlPlaceholder}
                disabled={busy}
              />
            </Field>
            <div className="flex justify-end">
              <Button onClick={doImport} disabled={busy || url.trim() === ""}>
                {busy ? <Spinner /> : <Download size={15} />} {isc.importPlaylistButton}
              </Button>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader
            title={isc.likesCardTitle}
            subtitle={status?.username
              ? isc.likesSubtitleWithUser(status.username)
              : isc.likesSubtitleNoUser}
            action={status?.username ? (
              <Button size="sm" variant="outline" onClick={() => router.push("/playlists/import-soundcloud/likes")}>
                <Heart size={15} /> {t.playlists.openButton}
              </Button>
            ) : (
              <Button size="sm" variant="outline" onClick={() => router.push("/settings")}>
                <Settings size={15} /> {t.nav.settings}
              </Button>
            )}
          />
        </Card>
      </div>
    </PageLayout>
  );
}
