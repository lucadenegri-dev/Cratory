"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { LabelStats, LibraryStats } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { EqMeter } from "@/components/ui";
import { Histogram } from "@/components/dashboard/histogram";
import { CamelotMatrix } from "@/components/statistics/camelot-matrix";

/* Composizione editoriale, non griglia a celle uguali: la vecchia versione
   metteva ogni sezione in un `grid-cols-2` che imponeva a tutte le celle
   l'altezza della piu' alta (l'istogramma BPM, alto 56px, viveva in una cella
   alta 330 accanto alle 24 righe delle tonalita'). Qui ogni banda e' alta
   quanto il suo contenuto, e le due colonne si usano solo dove i due blocchi
   hanno davvero altezze paragonabili. */

function Band({ title, caption, children, className }: {
  title?: string; caption?: ReactNode; children: ReactNode; className?: string;
}) {
  return (
    <section className={`border-t border-border p-5 ${className ?? ""}`}>
      {title && (
        <div className="mb-3 flex items-baseline gap-2">
          <h2 className="text-[10px] font-semibold uppercase tracking-wider text-fg-strong">{title}</h2>
          {caption && <span className="text-[10px] uppercase tracking-wider text-muted">{caption}</span>}
        </div>
      )}
      {children}
    </section>
  );
}

/* Cifra del colophon: etichetta minuscola sopra, numero tabulare sotto. Restano
   deliberatamente a `text-xl` — e' un frontespizio tipografico, non una fila di
   hero-metric. */
/* Due bande affiancate solo se ci sono entrambe: con una sola, quella resta a
   piena larghezza invece di lasciare mezza riga vuota (le sezioni senza dati
   non vengono rese). Il filetto verticale sta sul contenitore della destra,
   così corre per tutta l'altezza della coppia. */
function TwoUp({ left, right, cols }: { left: ReactNode; right: ReactNode; cols: string }) {
  // `||`, non `??`: i chiamanti passano `cond && <Band/>`, quindi il ramo
  // assente arriva come `false`, che `??` lascerebbe passare.
  if (!left || !right) return <>{left || right || null}</>;
  return (
    <div className={`md:grid ${cols}`}>
      {left}
      <div className="border-border md:border-l">{right}</div>
    </div>
  );
}

function Figure({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="bg-bg px-4 py-3">
      <div className="text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div className="tnum mt-1 text-xl text-fg-strong">{value}</div>
    </div>
  );
}

type BarRow = { label: string; value: number; href?: string };

/* Lista ordinata: la colonna dell'etichetta e' `auto` e le righe sono subgrid,
   quindi si dimensiona sul nome piu' lungo e resta incolonnata — invece del
   `w-20` fisso di MiniBars, che a piena pagina troncava «Orange Milk Reco…»
   con 700px di barra vuota accanto. */
function RankedBars({ rows, scale, labelClass = "max-w-48" }: {
  rows: BarRow[]; scale?: number; labelClass?: string;
}) {
  // `scale` esplicita quando la lista e' spezzata in piu' colonne: senza, ogni
  // colonna si normalizzerebbe sul proprio massimo e la prima label della
  // seconda colonna disegnerebbe una barra lunga quanto quella della prima.
  const max = Math.max(1, scale ?? 0, ...rows.map((r) => r.value));
  return (
    <div className="grid grid-cols-[auto_minmax(3rem,1fr)_auto] items-center gap-x-3 gap-y-1.5">
      {rows.map((r) => {
        const body = (
          <>
            <span className={`${labelClass} truncate text-xs text-muted group-hover:text-fg-strong`} title={r.label}>{r.label}</span>
            <span className="h-2 bg-elevated">
              <span className="block h-full bg-fg transition-colors group-hover:bg-fg-strong"
                style={{ width: `${Math.max(2, Math.round((r.value / max) * 100))}%` }} />
            </span>
            <span className="tnum text-xs text-fg-strong">{r.value}</span>
          </>
        );
        const cls = "group col-span-3 grid grid-cols-subgrid items-center";
        return r.href
          ? <Link key={r.label} href={r.href} className={cls}>{body}</Link>
          : <div key={r.label} className={cls}>{body}</div>;
      })}
    </div>
  );
}

/* Quattro fonti sono una composizione, non una classifica: una barra unica
   segmentata dice «di cosa e' fatta la libreria» in una riga. Monocroma per
   tono (fg → fg/25), separata da filetti di 1px (gap-px sul fondo `border`). */
const SOURCE_TONE = ["bg-fg", "bg-fg/70", "bg-fg/45", "bg-fg/25"];

function SourceSplit({ rows, total }: { rows: BarRow[]; total: number }) {
  return (
    <div>
      <div className="flex h-3 gap-px bg-border">
        {rows.map((r, i) => (
          <span key={r.label} className={SOURCE_TONE[i] ?? "bg-fg/25"}
            style={{ width: `${(r.value / Math.max(1, total)) * 100}%` }} />
        ))}
      </div>
      <div className="mt-3 space-y-1.5">
        {rows.map((r, i) => (
          <div key={r.label} className="flex items-center gap-2 text-xs">
            <span className={`h-2 w-2 shrink-0 ${SOURCE_TONE[i] ?? "bg-fg/25"}`} />
            <span className="text-muted">{r.label}</span>
            <span className="tnum ml-auto text-fg-strong">{r.value}</span>
            <span className="tnum w-10 text-right text-muted">{Math.round((r.value / Math.max(1, total)) * 100)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function EnergyStrip({ rows, flat }: { rows: { from: number; to: number; count: number }[]; flat: boolean }) {
  const t = useT();
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div>
      {/* Tono ridotto rispetto all'istogramma BPM: la distribuzione di `energy`
          e' derivata e tende a spalmarsi, quindi la sezione esiste per
          completezza — non deve pesare quanto quella che porta il dato. */}
      <div className="flex h-8 items-end gap-1">
        {rows.map((r) => (
          <span key={r.from} className="flex-1 bg-fg/50" title={`${r.from}–${r.to} · ${r.count}`}
            style={{ height: `${Math.max(4, Math.round((r.count / max) * 100))}%` }} />
        ))}
      </div>
      <div className="mt-1 flex gap-1">
        {rows.map((r) => <span key={r.from} className="tnum flex-1 text-center text-[10px] text-muted">{r.count}</span>)}
      </div>
      <div className="mt-2 flex items-baseline justify-between border-t border-border pt-1.5 text-[10px] uppercase tracking-wider text-muted">
        <span className="tnum">{rows[0]?.from ?? 0}</span>
        {flat && <span>{t.stats.energyFlat}</span>}
        <span className="tnum">{rows[rows.length - 1]?.to ?? 100}</span>
      </div>
    </div>
  );
}

/** Il ritratto completo della libreria: tutto ciò che il colophon della
 *  dashboard riassumeva, qui a grafici pieni. Solo presentazione: i dati
 *  arrivano già caricati dalla route. */
export function StatisticsView({ stats, labels }: { stats: LibraryStats; labels: LabelStats[] }) {
  const t = useT();

  const genreEntries = Object.entries(stats.genre_distribution ?? {}).sort((a, b) => b[1] - a[1]);
  const genreRows: BarRow[] = genreEntries.slice(0, 12)
    .map(([g, n]) => ({ label: g, value: n, href: `/library?genre=${encodeURIComponent(g)}` }));
  const genreTail = genreEntries.length - genreRows.length;

  const labelRows: BarRow[] = labels.slice(0, 10).map((l) => ({
    label: l.label, value: l.track_count, href: `/labels/${encodeURIComponent(l.label)}`,
  }));
  const labelScale = Math.max(1, ...labelRows.map((r) => r.value));

  const SOURCE_LABEL: Record<string, string> = {
    spotify: t.library.sourceSpotifyOption,
    soundcloud: t.library.sourceSoundcloudOption,
    manual: t.library.sourceManualOption,
    local_files: t.library.sourceLocalFilesOption,
  };
  const sourceRows: BarRow[] = Object.entries(stats.by_source ?? {})
    .sort((a, b) => b[1] - a[1])
    .map(([s, n]) => ({ label: SOURCE_LABEL[s] ?? s, value: n }));
  const sourceTotal = sourceRows.reduce((acc, r) => acc + r.value, 0);

  const energy = stats.energy_distribution ?? [];
  // Piatta = lo scarto fra il bucket piu' e meno popolato sta sotto il 15% del
  // massimo: e' il caso della distribuzione di `energy`, che essendo derivata
  // deterministicamente tende a spalmarsi. Vale la pena dirlo invece di
  // lasciar leggere cinque barre identiche come se fossero un dato.
  const energyFlat = energy.length > 1 && (() => {
    const counts = energy.map((b) => b.count);
    const max = Math.max(...counts);
    return max > 0 && (max - Math.min(...counts)) / max < 0.15;
  })();

  const hasKeys = Object.keys(stats.key_distribution ?? {}).length > 0;
  const readyPct = stats.total_tracks > 0 ? Math.round((stats.ready_for_set / stats.total_tracks) * 100) : 0;
  const notReady = stats.total_tracks - stats.ready_for_set;
  const bpmRange = stats.bpm_min != null && stats.bpm_max != null
    ? `${Math.round(stats.bpm_min)}–${Math.round(stats.bpm_max)}` : "—";

  return (
    <div className="border border-border">
      {/* Colophon: il frontespizio che mancava del tutto — la pagina apriva su
          un istogramma senza dire di quante tracce stesse parlando. Sei celle
          (divisibili per 2, 3 e 6) così nessuna riga resta spaiata a ogni
          breakpoint e i filetti di `gap-px` non lasciano buchi. */}
      <div className="grid grid-cols-2 gap-px bg-border sm:grid-cols-3 lg:grid-cols-6">
        <Figure label={t.stats.figTracks} value={stats.total_tracks} />
        <Figure label={t.stats.figOwned} value={stats.with_local_file} />
        <Figure label={t.stats.figPlaylists} value={stats.playlists} />
        <Figure label={t.stats.figGenres} value={genreEntries.length} />
        <Figure label={t.stats.figLabels} value={labels.length} />
        <Figure label={t.stats.figBpmRange} value={bpmRange} />
      </div>

      {stats.bpm_histogram.length > 0 && (
        <Band title={t.stats.bpm}>
          <Histogram bins={stats.bpm_histogram} height="h-20" />
        </Band>
      )}

      <TwoUp
        cols="md:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]"
        left={hasKeys && (
          <Band title={t.stats.keys} caption={t.stats.keysWheel}>
            <CamelotMatrix distribution={stats.key_distribution ?? {}} />
          </Band>
        )}
        right={genreRows.length > 0 && (
          <Band title={t.stats.genres} caption={genreTail > 0 ? t.stats.genresTail(genreTail) : undefined}>
            <RankedBars rows={genreRows} />
          </Band>
        )}
      />

      {labelRows.length > 0 && (
        <Band title={t.stats.labels} caption={labels.length > labelRows.length ? t.stats.labelsOf(labelRows.length, labels.length) : undefined}>
          {/* Larghezza fissa dell'etichetta solo qui: le due colonne sono due
              griglie distinte e senza un valore condiviso partirebbero da due
              ascisse diverse. 10rem copre «Orange Milk Records». */}
          <div className="grid gap-x-10 gap-y-1.5 md:grid-cols-2">
            <RankedBars rows={labelRows.slice(0, 5)} scale={labelScale} labelClass="w-40" />
            {labelRows.length > 5 && <RankedBars rows={labelRows.slice(5)} scale={labelScale} labelClass="w-40" />}
          </div>
        </Band>
      )}

      <TwoUp
        cols="md:grid-cols-2"
        left={sourceRows.length > 0 && (
          <Band title={t.stats.sources}>
            <SourceSplit rows={sourceRows} total={sourceTotal} />
          </Band>
        )}
        right={energy.length > 0 && (
          <Band title={t.stats.energy}>
            <EnergyStrip rows={energy} flat={!!energyFlat} />
          </Band>
        )}
      />

      {/* Copertura: era tre barre al 95% una sopra l'altra. Il dato utile e'
          quante tracce mancano e dove andare a prenderle. */}
      {stats.total_tracks > 0 && (
        <Band title={t.stats.coverage}>
          {/* Il meter resta l'EqMeter `calm` (la grammatica documentata per i
              rapporti statici) ma limitato in larghezza: a piena pagina i suoi
              blocchi da 8px diventano un codice a barre. */}
          <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
            <span className="flex items-baseline gap-2">
              <span className="tnum text-lg text-fg-strong">{stats.ready_for_set}</span>
              <span className="tnum text-sm text-muted">/ {stats.total_tracks}</span>
              <span className="text-[10px] uppercase tracking-wider text-muted">{t.stats.coverageReady}</span>
            </span>
            <EqMeter value={readyPct} calm className="h-4 w-full max-w-sm" />
            {notReady > 0 && (
              <Link href="/library?incomplete=1"
                className="text-xs text-muted underline-offset-4 transition-colors hover:text-fg-strong hover:underline">
                {t.stats.coverageMissing(notReady)} →
              </Link>
            )}
          </div>
        </Band>
      )}
    </div>
  );
}
