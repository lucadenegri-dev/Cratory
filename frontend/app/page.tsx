"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Music, Gauge, Sparkles, Compass, ArrowRight, Pencil, Tags, KeyRound, FolderOpen, RefreshCw,
} from "lucide-react";
import {
  apiGet, getLabels, getPipeline, listImportedPlaylists, fmtDate,
  type LibraryStats, type LabelStats, type SetlistSummary, type Playlist, type PipelineStatus,
} from "@/lib/api";
import { PipelineStrip } from "@/components/dashboard/pipeline";
import { Card, Alert, Progress, Button, Badge, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { Figure } from "@/components/dashboard/figure";
import { Histogram } from "@/components/dashboard/histogram";
import { MiniBars, type MiniBarRow } from "@/components/dashboard/mini-bars";
import { RecentList, type RecentItem } from "@/components/dashboard/recent-list";

/* ----------------------------------------------------- helper di sezione */

function ColHead({ children }: { children: React.ReactNode }) {
  return <div className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-fg-strong">{children}</div>;
}

function SubLabel({ icon, children }: { icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="mb-2 mt-4 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted first:mt-0">
      {icon && <span className="text-faint">{icon}</span>}{children}
    </div>
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

function QuickAction({ href, title, desc }: { href: string; title: string; desc: string }) {
  return (
    <Link href={href} className="group flex-1 px-5 py-5 transition-colors hover:bg-elevated">
      <div className="flex items-center justify-between gap-2">
        <span className="text-base font-semibold uppercase tracking-wide text-fg-strong">{title}</span>
        <ArrowRight size={17} className="shrink-0 text-muted transition-transform group-hover:translate-x-1 group-hover:text-fg-strong" />
      </div>
      <div className="mt-1 text-xs text-muted">{desc}</div>
    </Link>
  );
}

/* --------------------------------------------------------- raccomandazione */

type Reco = { icon: React.ReactNode; tag: string; title: string; desc?: string; href: string; cta: string };

/** "Prossimo passo" suggerito: guida l'utente nel ciclo (anche cross-app) in base allo stato. */
function recommend(s: LibraryStats, p: PipelineStatus | null): Reco | null {
  if (s.total_tracks === 0) return null; // gestito dall'empty state
  if (p && (p.inbox_files ?? 0) > 0) {
    return {
      icon: <FolderOpen size={22} />, tag: "Prossimo passo", title: "Organizza i download",
      desc: `${p.inbox_files} file in inbox aspettano il triage e l'organizzazione (DJPlayer → DjOrganizer).`,
      href: p.organizer_url ?? "/downloads", cta: p.organizer_url ? "Apri DjOrganizer" : "Vedi download",
    };
  }
  if (p?.index_mismatch) {
    return {
      icon: <RefreshCw size={22} />, tag: "Prossimo passo", title: "La Libreria è cambiata",
      desc: "I file su disco non coincidono con le tracce possedute: lancia una scansione dalla striscia qui sopra o dalla Libreria.",
      href: "/library", cta: "Vai alla Libreria",
    };
  }
  const keyPct = s.total_tracks ? s.with_key / s.total_tracks : 0;
  if (keyPct < 0.6) {
    return {
      icon: <Gauge size={22} />, tag: "Prossimo passo", title: "Completa BPM e tonalità",
      desc: `${s.with_key} tracce su ${s.total_tracks} hanno la tonalità. Analizza in Rekordbox e importa la collezione (fase Analizza qui sopra) o inserisci i valori a mano per sbloccare il Set Builder.`,
      href: "/library", cta: "Valori a mano",
    };
  }
  if (s.ready_for_set > 0) {
    return {
      icon: <Sparkles size={22} />, tag: "Prossimo passo", title: "Sei pronto per un set",
      href: "/set-builder", cta: "Costruisci un set",
    };
  }
  return {
    icon: <Compass size={22} />, tag: "Prossimo passo", title: "Espandi la libreria",
    desc: "Scopri tracce affini al gusto delle tue playlist e aggiungile alla libreria.",
    href: "/discovery", cta: "Scopri musica",
  };
}

/* ------------------------------------------------------------------ page */

export default function Dashboard() {
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [labels, setLabels] = useState<LabelStats[]>([]);
  const [sets, setSets] = useState<SetlistSummary[] | null>(null);
  const [playlists, setPlaylists] = useState<Playlist[] | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<LibraryStats>("/api/stats").then((s) => { setStats(s); setError(null); }).catch((e) => setError(String(e.message ?? e)));
    getPipeline().then(setPipeline).catch(() => setPipeline(null));
    getLabels().then(setLabels).catch(() => {});
    apiGet<SetlistSummary[]>("/api/sets").then(setSets).catch(() => setSets([]));
    listImportedPlaylists().then(setPlaylists).catch(() => setPlaylists([]));
  }, []);
  useEffect(load, [load]);

  const empty = stats != null && stats.total_tracks === 0;
  const reco = stats ? recommend(stats, pipeline) : null;

  const keyRows: MiniBarRow[] = stats
    ? Object.entries(stats.key_distribution)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 8)
        .map(([k, n]) => ({ label: k, value: n }))
    : [];

  const labelRows: MiniBarRow[] = labels.slice(0, 5).map((l) => ({
    label: l.label, value: l.track_count, href: `/labels/${encodeURIComponent(l.label)}`,
  }));

  const recentSets: RecentItem[] = (sets ?? [])
    .slice()
    .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))
    .slice(0, 4)
    .map((s, i) => ({ n: String(i + 1).padStart(2, "0"), title: s.name, meta: fmtDate(s.created_at), href: `/sets/${s.id}` }));

  const recentPlaylists: RecentItem[] = (playlists ?? [])
    .slice()
    .sort((a, b) => (a.imported_at < b.imported_at ? 1 : -1))
    .slice(0, 3)
    .map((p, i) => ({ n: String(i + 1).padStart(2, "0"), title: p.name, meta: `${p.track_count} tr.`, href: `/playlists/${p.id}` }));

  return (
    <PageLayout>
      {error && <div className="mb-6"><Alert tone="danger">⚠ {error} — il backend è attivo su :8000?</Alert></div>}

      {!stats && !error && <Loading />}

      {empty && (
        <Card>
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <Music size={36} className="text-faint" />
            <div>
              <p className="font-medium text-fg-strong">Nessuna playlist ancora</p>
              <p className="mt-1 text-sm text-muted">Importa una playlist Spotify per iniziare a costruire un set.</p>
            </div>
            <Link href="/playlists" className="inline-flex items-center gap-1.5 bg-fg-strong px-4 py-2 text-xs font-medium uppercase tracking-wider text-bg transition-colors hover:bg-fg">
              Importa una playlist <ArrowRight size={14} />
            </Link>
          </div>
        </Card>
      )}

      {/* Striscia di orientamento: le sei fasi del ciclo con contatori vivi */}
      {!empty && pipeline && (
        <div className="mb-6">
          <PipelineStrip p={pipeline} onRefresh={load} />
        </div>
      )}

      {stats && !empty && (
        <>
          {/* Figure hero */}
          <div className="grid grid-cols-4 border-l border-t border-border">
            <Figure label="Tracce" value={stats.total_tracks} />
            <Figure label="Playlist" value={stats.playlists} />
            <Figure label="Set salvati" value={sets ? sets.length : "—"} />
            {/* Possesso disk-first: quante tracce hanno il file in libreria */}
            <Figure
              label="Possedute"
              value={(
                <>
                  {stats.with_local_file}
                  {stats.total_tracks > 0 && (
                    <span className="ml-1.5 text-xs font-normal text-muted">
                      {Math.round((stats.with_local_file / stats.total_tracks) * 100)}%
                    </span>
                  )}
                </>
              )}
            />
          </div>

          {/* Prossimo passo */}
          {reco && (
            <Card className="mt-3">
              <div className="flex flex-wrap items-center gap-4 p-5">
                <span className="grid h-12 w-12 shrink-0 place-items-center rounded-none bg-elevated text-muted">{reco.icon}</span>
                <div className="min-w-0 flex-1">
                  <Badge tone="primary" className="mb-1.5">{reco.tag}</Badge>
                  <div className="font-semibold text-fg-strong">{reco.title}</div>
                  {reco.desc && <p className="text-sm text-muted">{reco.desc}</p>}
                </div>
                <Link href={reco.href}><Button>{reco.cta} <ArrowRight size={15} /></Button></Link>
              </div>
            </Card>
          )}

          {/* Tre colonne */}
          <div className="mt-3 grid border border-border lg:grid-cols-3">
            <section className="border-b border-border p-5 lg:border-b-0 lg:border-r">
              <ColHead>Forma della libreria</ColHead>
              <SubLabel icon={<Gauge size={12} />}>Istogramma BPM{stats.bpm_min ? ` · ${stats.bpm_min.toFixed(0)}–${stats.bpm_max?.toFixed(0)}` : ""}</SubLabel>
              <Histogram bins={stats.bpm_histogram} />
              <SubLabel icon={<KeyRound size={12} />}>Tonalità più frequenti</SubLabel>
              <MiniBars rows={keyRows} />
            </section>

            <section className="border-b border-border p-5 lg:border-b-0 lg:border-r">
              <ColHead>Attività recente</ColHead>
              <div className="mb-2 flex items-center justify-between">
                <SubLabel>Ultimi set</SubLabel>
                <Link href="/sets" className="text-[10px] uppercase tracking-wider text-muted hover:text-fg">Tutti →</Link>
              </div>
              <RecentList items={recentSets} empty="Nessun set ancora." />
              <div className="mb-2 mt-5 flex items-center justify-between">
                <SubLabel>Ultime playlist</SubLabel>
                <Link href="/playlists" className="text-[10px] uppercase tracking-wider text-muted hover:text-fg">Tutte →</Link>
              </div>
              <RecentList items={recentPlaylists} empty="Nessuna playlist ancora." />
            </section>

            <section className="p-5">
              <ColHead>Catalogo</ColHead>
              <SubLabel icon={<Gauge size={12} />}>Copertura BPM/key · energia</SubLabel>
              <div className="space-y-2.5">
                <Coverage label="BPM e tonalità" n={stats.with_key} total={stats.total_tracks} />
                <Coverage label="Energia" n={stats.with_features} total={stats.total_tracks} />
              </div>
              <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
                <Link href="/library" className="inline-flex items-center gap-1 text-xs text-muted hover:text-fg"><Pencil size={12} /> Valori a mano</Link>
              </div>
              <div className="mb-2 mt-5 flex items-center justify-between">
                <SubLabel icon={<Tags size={12} />}>Top etichette</SubLabel>
                <Link href="/labels" className="text-[10px] uppercase tracking-wider text-muted hover:text-fg">Tutte →</Link>
              </div>
              <MiniBars rows={labelRows} />
            </section>
          </div>

          {/* Azioni rapide */}
          <div className="mt-3 flex flex-col border border-border sm:flex-row sm:divide-x sm:divide-border">
            <QuickAction href="/playlists" title="Importa playlist" desc="Spotify, brani salvati o tracklist manuale" />
            <QuickAction href="/discovery" title="Scopri musica" desc="Tracce che potrebbero interessarti" />
            <QuickAction href="/shazam" title="Identifica un mix" desc="Riconosci le tracce di un DJ set" />
          </div>
        </>
      )}
    </PageLayout>
  );
}
