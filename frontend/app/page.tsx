"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Music, Gauge, KeyRound, CircleAlert, ArrowRight } from "lucide-react";
import { apiGet, type LibraryStats } from "@/lib/api";
import { Card, Alert } from "@/components/ui";

function Stat({ icon, label, value, accent }: { icon: React.ReactNode; label: string; value: React.ReactNode; accent?: boolean }) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted">
        <span className="text-faint">{icon}</span>{label}
      </div>
      <div className={`tnum mt-1.5 text-2xl font-semibold ${accent ? "text-primary" : ""}`}>{value}</div>
    </Card>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<LibraryStats>("/api/stats").then((s) => { setStats(s); setError(null); }).catch((e) => setError(String(e.message ?? e)));
  }, []);
  useEffect(load, [load]);

  const empty = stats && stats.total_tracks === 0;

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-muted">Panoramica della libreria.</p>
      </header>

      {error && <div className="mb-6"><Alert tone="danger">⚠ {error} — il backend è attivo su :8000?</Alert></div>}

      {empty && (
        <Card className="mb-6">
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <Music size={36} className="text-faint" />
            <div>
              <p className="font-medium">Libreria vuota</p>
              <p className="mt-1 text-sm text-muted">Importa una playlist Spotify per iniziare.</p>
            </div>
            <Link href="/playlists" className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-fg hover:bg-primary-hover">
              Vai alle Playlists <ArrowRight size={14} />
            </Link>
          </div>
        </Card>
      )}

      {stats && !empty && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat icon={<Music size={14} />} label="Tracce" value={stats.total_tracks} accent />
            <Stat icon={<Gauge size={14} />} label="Con BPM" value={stats.with_bpm} />
            <Stat icon={<KeyRound size={14} />} label="Con tonalità" value={stats.with_tonality} />
            <Stat icon={<CircleAlert size={14} />} label="Metadata mancanti" value={stats.missing_metadata} />
          </div>

          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            <Card className="p-4">
              <div className="mb-3 text-xs font-medium uppercase tracking-wide text-muted">Sorgenti</div>
              <div className="space-y-2">
                {(["spotify", "soundcloud", "local"] as const).map((s) => {
                  const n = stats.by_source[s] ?? 0;
                  const pct = stats.total_tracks ? (n / stats.total_tracks) * 100 : 0;
                  return (
                    <div key={s}>
                      <div className="mb-1 flex justify-between text-xs"><span className="capitalize text-muted">{s}</span><span className="tnum text-faint">{n}</span></div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-elevated"><div className="h-full rounded-full bg-primary" style={{ width: `${pct}%` }} /></div>
                    </div>
                  );
                })}
              </div>
            </Card>

            <Card className="p-4">
              <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Range BPM</div>
              <div className="tnum text-2xl font-semibold">{stats.bpm_min ? `${stats.bpm_min.toFixed(0)}–${stats.bpm_max?.toFixed(0)}` : "—"}</div>
              <Link href="/library" className="mt-3 inline-flex items-center gap-1 text-sm text-info hover:underline">Esplora la libreria <ArrowRight size={14} /></Link>
            </Card>

            <Card className="p-4">
              <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted">Tonalità (Camelot)</div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(stats.key_distribution).map(([k, n]) => (
                  <span key={k} className="tnum rounded-md bg-elevated px-1.5 py-0.5 text-xs text-muted" title={`${n} tracce`}>{k}<span className="text-faint">·{n}</span></span>
                ))}
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
