"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Music, Gauge, KeyRound, Sparkles, ListPlus, Compass, ArrowRight, ListMusic, CheckCircle2, Pencil,
  Radar, Tags,
} from "lucide-react";
import { apiGet, getLabels, type LibraryStats, type LabelStats } from "@/lib/api";
import { Card, Alert, Progress, Button, Badge } from "@/components/ui";

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

function Action({ href, icon, title, desc }: { href: string; icon: React.ReactNode; title: string; desc: string }) {
  return (
    <Link href={href} className="group flex items-center gap-3 rounded-[var(--radius)] border border-border bg-surface p-4 transition-colors hover:border-border-strong hover:bg-elevated/40">
      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-primary/15 text-primary">{icon}</span>
      <div className="min-w-0">
        <div className="flex items-center gap-1 font-medium">{title}<ArrowRight size={14} className="text-faint transition-transform group-hover:translate-x-0.5" /></div>
        <div className="truncate text-sm text-muted">{desc}</div>
      </div>
    </Link>
  );
}

function Coverage({ label, n, total }: { label: string; n: number; total: number }) {
  const pct = total ? Math.round((n / total) * 100) : 0;
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs"><span className="text-muted">{label}</span><span className="tnum text-muted">{n}/{total} · {pct}%</span></div>
      <Progress value={pct} />
    </div>
  );
}

function KeyDistribution({ dist }: { dist: Record<string, number> }) {
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return <span className="text-sm text-faint">—</span>;
  const max = Math.max(...entries.map(([, n]) => n));
  const top = entries.slice(0, 8);
  return (
    <div className="space-y-1.5">
      {top.map(([k, n]) => (
        <div key={k} className="flex items-center gap-2">
          <span className="tnum w-9 shrink-0 text-xs font-medium text-muted">{k}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-elevated">
            <div className="h-full rounded-full bg-primary/70" style={{ width: `${Math.max(6, Math.round((n / max) * 100))}%` }} />
          </div>
          <span className="tnum w-4 shrink-0 text-right text-xs text-muted">{n}</span>
        </div>
      ))}
      {entries.length > top.length && (
        <p className="pt-0.5 text-xs text-muted">+{entries.length - top.length} altre tonalità</p>
      )}
    </div>
  );
}

function LabelBars({ labels }: { labels: LabelStats[] }) {
  const top = labels.slice(0, 8);
  const max = Math.max(...top.map((l) => l.track_count), 1);
  return (
    <div className="space-y-1.5">
      {top.map((l) => (
        <Link key={l.label} href={`/labels/${encodeURIComponent(l.label)}`} className="group flex items-center gap-2">
          <span className="w-28 shrink-0 truncate text-xs font-medium text-muted group-hover:text-fg" title={l.label}>{l.label}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full bg-elevated">
            <div className="h-full rounded-full bg-primary/70" style={{ width: `${Math.max(6, Math.round((l.track_count / max) * 100))}%` }} />
          </div>
          <span className="tnum w-5 shrink-0 text-right text-xs text-muted">{l.track_count}</span>
        </Link>
      ))}
    </div>
  );
}

type Reco = { icon: React.ReactNode; tag: string; title: string; desc: string; href: string; cta: string };

/** "Prossimo passo" suggerito: guida l'utente nel flusso in base allo stato della libreria. */
function recommend(s: LibraryStats): Reco | null {
  if (s.total_tracks === 0) return null; // gestito dall'empty state
  const keyPct = s.total_tracks ? s.with_key / s.total_tracks : 0;
  if (keyPct < 0.6) {
    return {
      icon: <Gauge size={22} />, tag: "Prossimo passo", title: "Completa BPM e tonalità",
      desc: `${s.with_key} tracce su ${s.total_tracks} hanno la tonalità. Arricchisci le feature o inserisci i valori a mano per sbloccare il Set Builder.`,
      href: "/playlists", cta: "Arricchisci",
    };
  }
  if (s.ready_for_set > 0) {
    return {
      icon: <Sparkles size={22} />, tag: "Prossimo passo", title: "Sei pronto per un set",
      desc: `${s.ready_for_set} tracce pronte per il mix: genera una scaletta`,
      href: "/set-builder", cta: "Costruisci un set",
    };
  }
  return {
    icon: <Compass size={22} />, tag: "Prossimo passo", title: "Espandi la libreria",
    desc: "Scopri tracce compatibili per colmare i buchi delle tue playlist.",
    href: "/discovery", cta: "Scopri musica",
  };
}

export default function Dashboard() {
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [labels, setLabels] = useState<LabelStats[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<LibraryStats>("/api/stats").then((s) => { setStats(s); setError(null); }).catch((e) => setError(String(e.message ?? e)));
    getLabels().then(setLabels).catch(() => {});
  }, []);
  useEffect(load, [load]);

  const empty = stats && stats.total_tracks === 0;
  const reco = stats ? recommend(stats) : null;

  return (
    <div>
      <header className="mb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-1 text-sm text-muted">Importa, arricchisci, genera.</p>
      </header>

      {error && <div className="mb-6"><Alert tone="danger">⚠ {error} — il backend è attivo su :8000?</Alert></div>}

      {empty && (
        <Card className="mb-6">
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <Music size={36} className="text-faint" />
            <div>
              <p className="font-medium">Nessuna playlist ancora</p>
              <p className="mt-1 text-sm text-muted">Importa una playlist Spotify per iniziare a costruire un set.</p>
            </div>
            <Link href="/playlists" className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-fg hover:bg-primary-hover">
              Importa una playlist <ArrowRight size={14} />
            </Link>
          </div>
        </Card>
      )}

      {/* Prossimo passo consigliato */}
      {reco && (
        <Card className="mb-6 border-primary/30 bg-primary/[0.04]">
          <div className="flex flex-wrap items-center gap-4 p-5">
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-primary/15 text-primary">{reco.icon}</span>
            <div className="min-w-0 flex-1">
              <Badge tone="primary" className="mb-1.5">{reco.tag}</Badge>
              <div className="font-semibold">{reco.title}</div>
              <p className="text-sm text-muted">{reco.desc}</p>
            </div>
            <Link href={reco.href}><Button>{reco.cta} <ArrowRight size={15} /></Button></Link>
          </div>
        </Card>
      )}

      {/* Azioni rapide — il flusso dell'app */}
      <div className="mb-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <Action href="/playlists" icon={<ListPlus size={18} />} title="Importa playlist" desc="Spotify, brani salvati o tracklist manuale" />
        <Action href="/discovery" icon={<Compass size={18} />} title="Scopri musica" desc="Tracce che potrebbero interessarti" />
        <Action href="/shazam" icon={<Radar size={18} />} title="Identifica un mix" desc="Riconosci le tracce di un DJ set" />
      </div>

      {stats && !empty && (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat icon={<ListMusic size={14} />} label="Playlist" value={stats.playlists} />
            <Stat icon={<Music size={14} />} label="Tracce" value={stats.total_tracks} accent />
            <Stat icon={<CheckCircle2 size={14} />} label="Pronte per il set" value={stats.ready_for_set} />
            <Stat icon={<Gauge size={14} />} label="Con BPM" value={stats.with_bpm} />
          </div>

          <div className="mt-3 grid gap-3 lg:grid-cols-3">
            <Card className="p-4 lg:col-span-2">
              <div className="mb-3 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted"><Gauge size={13} className="text-faint" /> Copertura enrichment</div>
              <div className="space-y-2.5">
                <Coverage label="BPM e tonalità (Camelot)" n={stats.with_key} total={stats.total_tracks} />
                <Coverage label="Mood / energia" n={stats.with_features} total={stats.total_tracks} />
                <Coverage label="Pronte per il set" n={stats.ready_for_set} total={stats.total_tracks} />
              </div>
              <div className="mt-3 flex flex-wrap gap-4">
                <Link href="/settings" className="inline-flex items-center gap-1 text-sm text-info hover:underline">Arricchisci le feature <ArrowRight size={14} /></Link>
                <Link href="/library" className="inline-flex items-center gap-1 text-sm text-muted hover:text-fg"><Pencil size={13} /> Inserisci i valori a mano</Link>
              </div>
            </Card>

            <Card className="p-4">
              <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted">Range BPM</div>
              <div className="tnum text-2xl font-semibold">{stats.bpm_min ? `${stats.bpm_min.toFixed(0)}–${stats.bpm_max?.toFixed(0)}` : "—"}</div>
              <div className="mb-2 mt-4 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted"><KeyRound size={13} className="text-faint" /> Tonalità più frequenti</div>
              <KeyDistribution dist={stats.key_distribution} />
            </Card>
          </div>

          <Card className="mt-3 p-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-muted"><Tags size={13} className="text-faint" /> Top etichette</div>
              <Link href="/labels" className="inline-flex items-center gap-1 text-sm text-info hover:underline">Tutte le etichette <ArrowRight size={14} /></Link>
            </div>
            {labels.length > 0
              ? <LabelBars labels={labels} />
              : <p className="text-sm text-muted">Nessuna etichetta ancora. <Link href="/labels" className="text-info hover:underline">Recuperale da Spotify</Link> per esplorare la libreria per etichetta.</p>}
          </Card>
        </>
      )}
    </div>
  );
}
