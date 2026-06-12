"use client";

import { useCallback, useEffect, useState } from "react";
import { apiGet, uploadXml, type LibraryStats } from "@/lib/api";

function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
      <div className="text-2xl font-semibold">{value}</div>
      <div className="mt-1 text-xs text-zinc-400">{label}</div>
    </div>
  );
}

export default function Dashboard() {
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<Record<string, unknown> | null>(null);

  const load = useCallback(() => {
    apiGet<LibraryStats>("/api/stats").then(setStats).catch((e) => setError(String(e.message ?? e)));
  }, []);

  useEffect(load, [load]);

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    setError(null);
    try {
      const report = await uploadXml(file);
      setImportResult(report.stats);
      load();
    } catch (err) {
      setError(String((err as Error).message ?? err));
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  }

  return (
    <div className="max-w-5xl">
      <h2 className="mb-4 text-2xl font-bold">Dashboard</h2>

      <section className="mb-6 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <h3 className="mb-2 font-semibold">Import libreria Rekordbox</h3>
        <p className="mb-3 text-sm text-zinc-400">
          Carica l&apos;export XML di Rekordbox. Il re-import aggiorna le tracce esistenti senza duplicarle.
        </p>
        <input
          type="file"
          accept=".xml,text/xml"
          onChange={onUpload}
          disabled={importing}
          className="block text-sm file:mr-3 file:rounded file:border-0 file:bg-emerald-600 file:px-4 file:py-2 file:text-white file:cursor-pointer hover:file:bg-emerald-500"
        />
        {importing && <p className="mt-2 text-sm text-amber-400">Import in corso…</p>}
        {importResult && (
          <pre className="mt-3 max-h-64 overflow-auto rounded bg-zinc-950 p-3 text-xs text-emerald-300">
            {JSON.stringify(importResult, null, 2)}
          </pre>
        )}
      </section>

      {error && <p className="mb-4 rounded bg-red-950 p-3 text-sm text-red-300">⚠ {error} — il backend è avviato su :8000?</p>}

      {stats && (
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard label="Tracce totali" value={stats.total_tracks} />
            <StatCard label="Con BPM" value={stats.with_bpm} />
            <StatCard label="Con tonalità" value={stats.with_tonality} />
            <StatCard label="Con cue point" value={stats.with_cues} />
            <StatCard label="Spotify" value={stats.by_source["spotify"] ?? 0} />
            <StatCard label="SoundCloud" value={stats.by_source["soundcloud"] ?? 0} />
            <StatCard label="File locali" value={stats.by_source["local"] ?? 0} />
            <StatCard label="Metadata mancanti" value={stats.missing_metadata} />
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <h3 className="mb-2 text-sm font-semibold text-zinc-300">Range BPM</h3>
              <p className="text-xl">
                {stats.bpm_min ? `${stats.bpm_min.toFixed(0)} – ${stats.bpm_max?.toFixed(0)}` : "—"}
              </p>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900 p-4">
              <h3 className="mb-2 text-sm font-semibold text-zinc-300">Distribuzione tonalità</h3>
              <div className="flex flex-wrap gap-1">
                {Object.entries(stats.key_distribution).map(([k, n]) => (
                  <span key={k} className="rounded bg-zinc-800 px-2 py-0.5 text-xs">
                    {k}: {n}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
