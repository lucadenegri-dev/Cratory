"use client";

import Link from "next/link";
import { use, useCallback, useEffect, useState } from "react";
import { ArrowLeft, Wand2, Compass } from "lucide-react";
import {
  getPlaylist, discoverExpand, discoveryStatus,
  type Playlist, type DiscoveryResponse, type DiscoveryStatus,
} from "@/lib/api";
import { Alert, Button, Checkbox, EmptyState, Spinner } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { ExpandResults } from "@/components/expand-results";

function err(e: unknown): string {
  return String((e as { message?: string })?.message ?? e);
}

export default function ExpandPlaylistPage({ params }: { params: Promise<{ id: string }> }) {
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
      setError(err(e));
    } finally {
      setBusy(false);
    }
  }, [pid]);

  useEffect(() => {
    getPlaylist(pid).then(setPlaylist).catch((e) => setError(err(e)));
    discoveryStatus().then(setStatus).catch(() => setStatus(null));
    run(false); // autorun senza AI
  }, [pid, run]);

  const marginalia = (
    <div className="space-y-3">
      <Checkbox
        label={status?.ai_explanations ? "Spiega con l'AI" : "Spiegazioni AI (configura AI_API_KEY)"}
        checked={aiEnabled}
        onChange={setUseAi}
        disabled={busy || !status?.ai_explanations}
      />
      <Button size="sm" variant="outline" className="w-full" onClick={() => run(aiEnabled)} disabled={busy}>
        {busy ? <Spinner /> : <Wand2 size={15} />} Ricalcola
      </Button>
    </div>
  );

  return (
    <PageLayout title="Espandi" meta={playlist?.name} marginaliaTitle="Opzioni" marginalia={marginalia}>
      <Link href={`/playlists/${pid}`} className="mb-4 inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        <ArrowLeft size={15} /> {playlist?.name ?? "Playlist"}
      </Link>

      {error && <Alert tone="danger">⚠ {error}</Alert>}

      {status && !status.configured && (
        <div className="mb-6">
          <Alert tone="info">
            Discovery non configurato: imposta <code className="font-mono">LASTFM_API_KEY</code> in
            <span className="font-medium"> backend/.env</span> (chiave gratuita su last.fm/api).
          </Alert>
        </div>
      )}

      {busy && !result && (
        <div className="flex items-center gap-2 text-sm text-muted"><Spinner /> Cerco tracce affini…</div>
      )}
      {result && <ExpandResults result={result} playlistId={pid} />}
      {!busy && !result && !error && (
        <EmptyState icon={<Compass size={28} />} title="Pronto per l'espansione">
          Premi “Ricalcola” per cercare tracce di gusto affine a questa playlist.
        </EmptyState>
      )}
    </PageLayout>
  );
}
