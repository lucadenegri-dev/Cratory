"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { ArrowLeft, Wand2, Compass } from "lucide-react";
import {
  getPlaylist, discoverExpand, discoveryStatus, errText,
  type Playlist, type DiscoveryResponse, type DiscoveryStatus,
} from "@/lib/api";
import { Alert, Button, Checkbox, EmptyState, Spinner } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { ExpandResults } from "@/components/expand-results";
import { useT } from "@/lib/i18n";

export default function ExpandPlaylistPage({ params }: { params: Promise<{ id: string }> }) {
  const t = useT();
  const { id } = use(params);
  const pid = Number(id);

  const [playlist, setPlaylist] = useState<Playlist | null>(null);
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [useAi, setUseAi] = useState(false); // autorun senza AI
  const [result, setResult] = useState<DiscoveryResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const aiEnabled = useAi && !!status?.ai_explanations;

  const run = useCallback(async (withAi: boolean) => {
    setBusy(true);
    setError(null);
    try {
      setResult(await discoverExpand(pid, { use_ai: withAi }));
    } catch (e) {
      setError(errText(e));
    } finally {
      setBusy(false);
    }
  }, [pid]);

  useEffect(() => {
    getPlaylist(pid).then(setPlaylist).catch((e) => setError(errText(e)));
    discoveryStatus().then(setStatus).catch(() => setStatus(null));
    const timer = setTimeout(() => run(false), 0); // autorun senza AI (deferred: niente setState sincrono nell'effect)
    return () => clearTimeout(timer);
  }, [pid, run]);

  const marginalia = (
    <div className="space-y-3">
      <Checkbox
        label={status?.ai_explanations ? t.playlists.expand.explainWithAi : t.playlists.expand.aiExplanationsDisabled}
        checked={aiEnabled}
        onChange={setUseAi}
        disabled={busy || !status?.ai_explanations}
      />
      <Button size="sm" variant="outline" className="w-full" onClick={() => run(aiEnabled)} disabled={busy}>
        {busy ? <Spinner /> : <Wand2 size={15} />} {t.playlists.expand.recalculateButton}
      </Button>
    </div>
  );

  return (
    <PageLayout title={t.playlists.expand.pageTitle} meta={playlist?.name} marginaliaTitle={t.playlists.marginaliaOptions} marginalia={marginalia}>
      <Link href={`/playlists/${pid}`} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> {playlist?.name ?? t.playlists.expand.backFallback}
      </Link>

      {error && <Alert tone="danger">⚠ {error}</Alert>}

      {status && !status.configured && (
        <div className="mb-6">
          <Alert tone="info">
            {t.playlists.expand.notConfiguredPrefix} <code className="font-mono">LASTFM_API_KEY</code> {t.playlists.expand.notConfiguredMiddle}
            <span className="font-medium"> backend/.env</span> {t.playlists.expand.notConfiguredSuffix}
          </Alert>
        </div>
      )}

      {busy && !result && (
        <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> {t.playlists.expand.searching}</div>
      )}
      {result && <ExpandResults result={result} playlistId={pid} />}
      {!busy && !result && !error && (
        <EmptyState icon={<Compass size={28} />} title={t.playlists.expand.emptyTitle}>
          {t.playlists.expand.emptyBody}
        </EmptyState>
      )}
    </PageLayout>
  );
}
