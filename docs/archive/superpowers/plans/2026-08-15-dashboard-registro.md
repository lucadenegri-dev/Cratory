# Dashboard «Il Registro» — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Riscrivere la prima pagina (`frontend/app/page.tsx`) come «Il Registro»: frontespizio tipografico, striscia pipeline invariata, sezione «Lavoro aperto» con code vive, colophon della libreria.

**Architecture:** Tre componenti nuovi/adattati sotto `frontend/components/dashboard/` (variante spark di `Histogram`, `Colophon`, `OpenWork`) composti da `page.tsx`, che aggiunge il fetch dei leads e un polling condizionale su `downloadStatus`+`getPipeline`. Nessuna modifica backend.

**Tech Stack:** Next.js 16 (App Router, client component), React, Tailwind con i token del design system, vitest + @testing-library/react.

**Spec:** `docs/archive/superpowers/specs/2026-08-15-dashboard-registro-design.md`

## Global Constraints

- Design system "archivio editoriale" al massimo, non oltre: monospace, monocromo, filetti 1px, geometria quadrata (`rounded-none`), `tnum` su ogni cifra. Nessun colore nuovo, nessuna ombra.
- Non toccare gli hunk della sessione parallela già nel working tree (`index-nav.tsx`, rimozione gaps in `page.tsx`/`playlists.ts`/i18n, `nav-organize.test.ts`): partire dallo stato attuale dei file e committare **solo i file elencati nel task** (`git add` per path espliciti, mai `git add -A`).
- `PipelineStrip` non si modifica.
- Entrambi i temi (dark e paper) devono leggere correttamente: usare solo token (`text-fg`, `text-muted`, `text-faint`, `border-border`, …), mai colori letterali.
- i18n: ogni stringa nuova in **entrambi** `frontend/lib/i18n/en.ts` e `frontend/lib/i18n/it.ts` (il tipo `Dictionary` impone la parità — se ne aggiungi una sola, TypeScript fallisce).
- Next 16: gli spazi dopo un elemento inline spariscono se il testo va a capo nel sorgente → usare `{" "}` esplicito dove serve uno spazio.
- Commit: messaggi in italiano stile repo (`feat(dashboard): …`), **senza** riga Co-Authored-By.
- Comandi da `frontend/`: test `npx vitest run tests/<file>.tsx`, lint `npm run lint`, build `npm run build`.

---

### Task 1: Variante «spark» di Histogram

**Files:**
- Modify: `frontend/components/dashboard/histogram.tsx`
- Test: `frontend/tests/histogram-spark.test.tsx` (nuovo)

**Interfaces:**
- Consumes: `BpmBin[]` da `@/lib/api` (già esistente: `{ from: number; to: number; count: number }`).
- Produces: `Histogram({ bins, variant })` con `variant?: "full" | "spark"`; default `"full"` identico a oggi. In `"spark"`: sparkline inline alta 14px, barrette `bg-faint`, bin modale `bg-fg`, nessun hover/label; con `bins` vuoto rende `null`.

- [ ] **Step 1: Scrivi il test che fallisce**

Crea `frontend/tests/histogram-spark.test.tsx`:

```tsx
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Histogram } from "@/components/dashboard/histogram";
import type { BpmBin } from "@/lib/api";

const BINS: BpmBin[] = [
  { from: 120, to: 124, count: 3 },
  { from: 124, to: 128, count: 9 },
  { from: 128, to: 132, count: 5 },
];

describe("histogram spark", () => {
  afterEach(cleanup);

  it("rende una barretta per bin, senza header né etichette min/max", () => {
    const { container } = render(<Histogram bins={BINS} variant="spark" />);
    const wrap = container.firstElementChild as HTMLElement;
    expect(wrap.getAttribute("aria-hidden")).toBe("true");
    expect(wrap.children.length).toBe(3);
    // Niente etichette BPM del rendering "full".
    expect(container.textContent).toBe("");
  });

  it("evidenzia il bin modale in fg, gli altri in faint", () => {
    const { container } = render(<Histogram bins={BINS} variant="spark" />);
    const bars = Array.from((container.firstElementChild as HTMLElement).children);
    expect(bars[1].className).toContain("bg-fg");
    expect(bars[0].className).toContain("bg-faint");
    expect(bars[2].className).toContain("bg-faint");
  });

  it("con bins vuoto non rende nulla (niente segnaposto nel colophon)", () => {
    const { container } = render(<Histogram bins={[]} variant="spark" />);
    expect(container.firstChild).toBeNull();
  });

  it("il rendering full resta invariato: barre interattive e range in calce", () => {
    const { container } = render(<Histogram bins={BINS} />);
    expect(container.querySelectorAll("button").length).toBe(3);
    expect(container.textContent).toContain("120");
    expect(container.textContent).toContain("132");
  });
});
```

- [ ] **Step 2: Verifica che fallisca**

Run: `cd frontend && npx vitest run tests/histogram-spark.test.tsx`
Expected: FAIL (i primi tre test — la prop `variant` non esiste, il rendering spark nemmeno; il quarto passa già).

- [ ] **Step 3: Implementa la variante**

In `frontend/components/dashboard/histogram.tsx`, aggiorna firma e aggiungi il ramo spark subito dopo il guard clause esistente (il ramo spark NON usa lo stato hover; `bg-fg` per il bin modale — a pari massimo va bene evidenziarli entrambi, `count === max` — e `bg-faint` per gli altri):

```tsx
export function Histogram({ bins, variant = "full" }: { bins: BpmBin[]; variant?: "full" | "spark" }) {
  const t = useT();
  const [hover, setHover] = useState<number | null>(null);
  if (variant === "spark") {
    if (bins.length === 0) return null;
    const max = Math.max(...bins.map((b) => b.count), 1);
    return (
      <span aria-hidden="true" className="inline-flex h-3.5 items-end gap-px align-middle">
        {bins.map((b, i) => (
          <span
            key={i}
            className={b.count === max ? "w-1 bg-fg" : "w-1 bg-faint"}
            style={{ height: `${Math.max(15, Math.round((b.count / max) * 100))}%` }}
          />
        ))}
      </span>
    );
  }
  if (bins.length === 0) return <p className="text-sm text-faint">—</p>;
  /* …resto invariato… */
```

Attenzione: `useState` resta chiamato prima del ramo (regola dei hook).

- [ ] **Step 4: Verifica che passi**

Run: `cd frontend && npx vitest run tests/histogram-spark.test.tsx`
Expected: PASS (4 test).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/dashboard/histogram.tsx frontend/tests/histogram-spark.test.tsx
git commit -m "feat(dashboard): variante spark di Histogram per il colophon"
```

---

### Task 2: Componente Colophon

**Files:**
- Create: `frontend/components/dashboard/colophon.tsx`
- Modify: `frontend/lib/i18n/it.ts` (sezione `dashboard`), `frontend/lib/i18n/en.ts` (sezione `dashboard`)
- Test: `frontend/tests/colophon.test.tsx` (nuovo)

**Interfaces:**
- Consumes: `LibraryStats`, `LabelStats` da `@/lib/api`; `Histogram` con `variant="spark"` dal Task 1.
- Produces: `Colophon({ stats, labels }: { stats: LibraryStats; labels: LabelStats[] })` — blocco chiuso tra filetti orizzontali con fino a 4 righe (BPM, tonalità, generi, label); ogni riga si omette se non ha dati.

- [ ] **Step 1: Aggiungi le chiavi i18n**

In `frontend/lib/i18n/it.ts`, dentro `dashboard: {`, aggiungi:

```ts
    colophonBpm: "BPM",
    colophonKeys: "Tonalità",
    colophonGenres: "Generi",
    colophonLabels: "Label",
```

In `frontend/lib/i18n/en.ts`, dentro `dashboard: {`, aggiungi:

```ts
    colophonBpm: "BPM",
    colophonKeys: "Keys",
    colophonGenres: "Genres",
    colophonLabels: "Labels",
```

- [ ] **Step 2: Scrivi il test che fallisce**

Crea `frontend/tests/colophon.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Colophon } from "@/components/dashboard/colophon";
import type { LabelStats, LibraryStats } from "@/lib/api";

function stats(over: Partial<LibraryStats> = {}): LibraryStats {
  return {
    total_tracks: 100, playlists: 4, by_source: {}, with_bpm: 90, with_key: 90,
    with_features: 0, with_local_file: 60, ready_for_set: 80, missing_metadata: 5,
    bpm_min: 120, bpm_max: 138,
    key_distribution: { "8A": 20, "5A": 15, "11B": 10, "3A": 8, "9B": 6, "1A": 2 },
    genre_distribution: { Techno: 40, House: 25, Electro: 10, Ambient: 5, Dub: 2 },
    bpm_histogram: [{ from: 120, to: 129, count: 40 }, { from: 129, to: 138, count: 50 }],
    energy_distribution: [],
    ...over,
  };
}

const LABELS: LabelStats[] = [
  { label: "Ostgut Ton", track_count: 12 },
  { label: "Hessle Audio", track_count: 9 },
  { label: "Livity Sound", track_count: 7 },
  { label: "Quarta", track_count: 1 },
] as LabelStats[];

describe("colophon", () => {
  afterEach(cleanup);

  it("rende il range BPM con la sparkline", () => {
    const { container } = render(<Colophon stats={stats()} labels={LABELS} />);
    expect(container.textContent).toContain("120–138");
    expect(container.querySelector('[aria-hidden="true"]')).toBeTruthy();
  });

  it("mostra le prime 5 tonalità, i primi 4 generi e le prime 3 label", () => {
    render(<Colophon stats={stats()} labels={LABELS} />);
    expect(screen.getByText("8A")).toBeTruthy();
    expect(screen.queryByText("1A")).toBeNull();       // sesta tonalità: fuori
    expect(screen.getByText("Techno")).toBeTruthy();
    expect(screen.queryByText("Dub")).toBeNull();       // quinto genere: fuori
    expect(screen.getByText("Ostgut Ton")).toBeTruthy();
    expect(screen.queryByText("Quarta")).toBeNull();    // quarta label: fuori
  });

  it("generi e label sono link alle rispettive pagine", () => {
    render(<Colophon stats={stats()} labels={LABELS} />);
    expect(screen.getByText("Techno").closest("a")?.getAttribute("href")).toBe("/library?genre=Techno");
    expect(screen.getByText("Ostgut Ton").closest("a")?.getAttribute("href")).toBe("/labels/Ostgut%20Ton");
  });

  it("omette le righe senza dati, niente segnaposto", () => {
    const vuote = stats({ bpm_min: null, bpm_max: null, bpm_histogram: [], key_distribution: {}, genre_distribution: {} });
    render(<Colophon stats={vuote} labels={[]} />);
    expect(screen.queryByText("BPM")).toBeNull();
    expect(screen.queryByText("Tonalità")).toBeNull();
    expect(screen.queryByText("Generi")).toBeNull();
    expect(screen.queryByText("Label")).toBeNull();
  });
});
```

- [ ] **Step 3: Verifica che fallisca**

Run: `cd frontend && npx vitest run tests/colophon.test.tsx`
Expected: FAIL — modulo `@/components/dashboard/colophon` inesistente.

- [ ] **Step 4: Implementa il componente**

Crea `frontend/components/dashboard/colophon.tsx`:

```tsx
"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { LabelStats, LibraryStats } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Histogram } from "./histogram";

/* Riga di colophon: etichetta maiuscola a sinistra, contenuto in linea che
   tronca con ellissi. Una riga senza dati non viene resa (il chiamante filtra). */
function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline gap-4 overflow-hidden whitespace-nowrap py-1.5">
      <span className="w-20 shrink-0 text-[10px] uppercase tracking-wider text-muted">{label}</span>
      <span className="truncate text-sm text-fg">{children}</span>
    </div>
  );
}

/** Il ritratto della libreria compresso come il colophon di un volume:
 *  righe tipografiche tra due filetti, non grafici a colonne. */
export function Colophon({ stats, labels }: { stats: LibraryStats; labels: LabelStats[] }) {
  const t = useT();
  const keys = Object.entries(stats.key_distribution).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const genres = Object.entries(stats.genre_distribution ?? {}).sort((a, b) => b[1] - a[1]).slice(0, 4);
  const tops = labels.slice(0, 3);
  const hasBpm = stats.bpm_min != null && stats.bpm_max != null;
  if (!hasBpm && keys.length === 0 && genres.length === 0 && tops.length === 0) return null;
  return (
    <div className="mt-6 divide-y divide-border border-y border-border">
      {hasBpm && (
        <Row label={t.dashboard.colophonBpm}>
          <span className="tnum text-fg-strong">{stats.bpm_min!.toFixed(0)}–{stats.bpm_max!.toFixed(0)}</span>
          <span className="ml-3 inline-block"><Histogram bins={stats.bpm_histogram} variant="spark" /></span>
        </Row>
      )}
      {keys.length > 0 && (
        <Row label={t.dashboard.colophonKeys}>
          {keys.map(([k, n]) => (
            <span key={k} className="mr-4">
              <span className="text-fg-strong">{k}</span>{" "}
              <span className="tnum text-muted">{n}</span>
            </span>
          ))}
        </Row>
      )}
      {genres.length > 0 && (
        <Row label={t.dashboard.colophonGenres}>
          {genres.map(([g, n]) => (
            <span key={g} className="mr-4">
              <Link href={`/library?genre=${encodeURIComponent(g)}`} className="text-fg-strong hover:underline">{g}</Link>{" "}
              <span className="tnum text-muted">{n}</span>
            </span>
          ))}
        </Row>
      )}
      {tops.length > 0 && (
        <Row label={t.dashboard.colophonLabels}>
          {tops.map((l) => (
            <span key={l.label} className="mr-4">
              <Link href={`/labels/${encodeURIComponent(l.label)}`} className="text-fg-strong hover:underline">{l.label}</Link>{" "}
              <span className="tnum text-muted">{l.track_count}</span>
            </span>
          ))}
        </Row>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Verifica che passi**

Run: `cd frontend && npx vitest run tests/colophon.test.tsx`
Expected: PASS (4 test).

- [ ] **Step 6: Commit**

```bash
git add frontend/components/dashboard/colophon.tsx frontend/tests/colophon.test.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(dashboard): colophon della libreria — BPM, tonalità, generi, label"
```

Nota: `it.ts`/`en.ts` hanno anche hunk della sessione parallela (rimozione chiavi gaps). Prima di committare: `git diff frontend/lib/i18n/it.ts` e verifica che gli hunk estranei non entrino nel commit — se `git add` per file li trascinerebbe, usa `git add -p frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts` selezionando solo i propri hunk (le 4 chiavi colophon).

---

### Task 3: Componente OpenWork («il banco»)

**Files:**
- Create: `frontend/components/dashboard/open-work.tsx`
- Modify: `frontend/lib/i18n/it.ts` (sezione `dashboard`), `frontend/lib/i18n/en.ts` (sezione `dashboard`)
- Test: `frontend/tests/open-work.test.tsx` (nuovo)

**Interfaces:**
- Consumes: `DownloadStatus`, `PipelineStatus`, `Track` da `@/lib/api`; `EqMeter` e `Badge` da `@/components/ui`; `fmtDate` da `@/lib/api`.
- Produces:
  - `OpenWork({ download, pending, inboxFiles, leads }: { download: DownloadStatus | null; pending: Track[]; inboxFiles: number | null; leads: Track[] })` — sezione `LAVORO APERTO` a righe condizionali numerate.
  - `queuesActive(download: DownloadStatus | null, pipeline: PipelineStatus | null): boolean` — `true` se il download è `running` o `pipeline.download_active`; il Task 4 la usa per accendere/spegnere il polling.

- [ ] **Step 1: Aggiungi le chiavi i18n**

In `frontend/lib/i18n/it.ts`, dentro `dashboard: {`:

```ts
    openWork: "Lavoro aperto",
    owDownloading: "Download in corso",
    owToReview: (n: number) => (n === 1 ? "1 download da rivedere" : `${n} download da rivedere`),
    owInbox: (n: number) => (n === 1 ? "1 file in inbox da sistemare" : `${n} file in inbox da sistemare`),
    owLeads: "Ultimi leads",
    owNone: "Nessun lavoro aperto",
```

In `frontend/lib/i18n/en.ts`, dentro `dashboard: {`:

```ts
    openWork: "Open work",
    owDownloading: "Downloading",
    owToReview: (n: number) => (n === 1 ? "1 download to review" : `${n} downloads to review`),
    owInbox: (n: number) => (n === 1 ? "1 file in the inbox to sort" : `${n} files in the inbox to sort`),
    owLeads: "Latest leads",
    owNone: "No open work",
```

- [ ] **Step 2: Scrivi il test che fallisce**

Crea `frontend/tests/open-work.test.tsx`:

```tsx
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { OpenWork, queuesActive } from "@/components/dashboard/open-work";
import type { DownloadStatus, PipelineStatus, Track } from "@/lib/api";

function dl(over: Partial<DownloadStatus> = {}): DownloadStatus {
  return {
    available: true, status: "idle", processed: 0, total: 0, downloaded: 0,
    needs_review: 0, not_found: 0, failed: 0, playlist_id: null, items: [],
    error: null, current_label: null, ...over,
  };
}

function track(over: Partial<Track> = {}): Track {
  return {
    id: 1, spotify_id: null, soundcloud_id: null, source_type: "spotify", platform: "spotify",
    title: "Tempo", artist: "Rrose", album: null, genre: null, year: null,
    duration_seconds: null, bpm: null, camelot_key: null, energy: null, label: null,
    status: "imported", url: null, isrc: null, playlists: [], added_at: "2026-08-14T10:00:00Z",
    playlist_added_at: null, spotify_url: null, album_art_url: null, has_local_file: false,
    local_path: null, local_format: null, local_bitrate: null, primary_file_id: null,
    genre_from_file: false, album_from_file: false, label_from_file: false, year_from_file: false,
    archived: false, rating: null, last_download_outcome: null, last_download_reason: null,
    last_download_path: null, ...over,
  } as Track;
}

describe("queuesActive", () => {
  const pipe = { download_active: false } as PipelineStatus;

  it("è vera solo con download running o download_active in pipeline", () => {
    expect(queuesActive(dl({ status: "running" }), pipe)).toBe(true);
    expect(queuesActive(dl(), { ...pipe, download_active: true } as PipelineStatus)).toBe(true);
    expect(queuesActive(dl(), pipe)).toBe(false);
    expect(queuesActive(null, null)).toBe(false);
  });
});

describe("open work", () => {
  afterEach(cleanup);

  it("senza nulla di pendente dichiara il vuoto, nessuna riga numerata", () => {
    render(<OpenWork download={dl()} pending={[]} inboxFiles={0} leads={[]} />);
    expect(screen.getByText("Nessun lavoro aperto")).toBeTruthy();
    expect(screen.queryByText("01")).toBeNull();
  });

  it("download running: progressbar reale e traccia in lavorazione", () => {
    render(
      <OpenWork
        download={dl({ status: "running", processed: 3, total: 10, current_label: "Rrose — Tempo" })}
        pending={[]} inboxFiles={0} leads={[]}
      />,
    );
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("30");
    expect(screen.getByText("Rrose — Tempo")).toBeTruthy();
    expect(screen.getByText("Download in corso").closest("a")?.getAttribute("href")).toBe("/wishlist");
  });

  it("le righe si numerano in sequenza solo per le sezioni visibili", () => {
    render(
      <OpenWork
        download={dl()} pending={[track({ id: 9, title: "Ecco", artist: "AAAA" })]}
        inboxFiles={4} leads={[track({ id: 2 })]}
      />,
    );
    // Tre sezioni visibili (revisione, inbox, leads) numerate 01/02/03.
    expect(screen.getByText("01")).toBeTruthy();
    expect(screen.getByText("02")).toBeTruthy();
    expect(screen.getByText("03")).toBeTruthy();
    expect(screen.queryByText("04")).toBeNull();
    expect(screen.getByText("1 download da rivedere").closest("a")?.getAttribute("href")).toBe("/wishlist");
    expect(screen.getByText("4 file in inbox da sistemare").closest("a")?.getAttribute("href")).toBe("/organize/files");
  });

  it("i leads mostrano artista — titolo, fonte e data, e linkano la traccia", () => {
    render(<OpenWork download={null} pending={[]} inboxFiles={null} leads={[track()]} />);
    expect(screen.getByText(/Rrose — Tempo/).closest("a")?.getAttribute("href")).toBe("/tracks/1");
    expect(screen.getByText("spotify")).toBeTruthy();
  });

  it("needs_review conta anche senza lista pending (fallback dal job)", () => {
    render(<OpenWork download={dl({ needs_review: 2 })} pending={[]} inboxFiles={0} leads={[]} />);
    expect(screen.getByText("2 download da rivedere")).toBeTruthy();
  });
});
```

- [ ] **Step 3: Verifica che fallisca**

Run: `cd frontend && npx vitest run tests/open-work.test.tsx`
Expected: FAIL — modulo `@/components/dashboard/open-work` inesistente.

- [ ] **Step 4: Implementa il componente**

Crea `frontend/components/dashboard/open-work.tsx`:

```tsx
"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import type { DownloadStatus, PipelineStatus, Track } from "@/lib/api";
import { fmtDate } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Badge, EqMeter } from "@/components/ui";

/** Le code si muovono? Decide se il polling della dashboard resta acceso. */
export function queuesActive(download: DownloadStatus | null, pipeline: PipelineStatus | null): boolean {
  return download?.status === "running" || pipeline?.download_active === true;
}

/* Riga da registro: numero progressivo in faint, contenuto a destra. */
function Row({ n, children }: { n: number; children: ReactNode }) {
  return (
    <div className="flex items-start gap-4 py-3">
      <span className="tnum pt-0.5 text-[10px] text-faint">{String(n).padStart(2, "0")}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}

type Props = {
  download: DownloadStatus | null;
  pending: Track[];
  inboxFiles: number | null;
  leads: Track[];
};

/** «Il banco»: il lavoro aperto sulla catena di acquisizione. Ogni riga compare
 *  solo se ha contenuto; il vuoto è dichiarato, mai riempito di segnaposto. */
export function OpenWork({ download, pending, inboxFiles, leads }: Props) {
  const t = useT();

  const running = download?.status === "running";
  const reviewCount = Math.max(pending.length, download?.needs_review ?? 0);
  const inbox = inboxFiles ?? 0;

  const rows: ReactNode[] = [];

  if (running && download) {
    const pct = download.total > 0 ? (download.processed / download.total) * 100 : null;
    rows.push(
      <Link key="dl" href="/wishlist" className="block transition-colors hover:bg-elevated">
        <div className="flex items-center justify-between gap-4">
          <span className="text-[10px] uppercase tracking-wider text-fg-strong">{t.dashboard.owDownloading}</span>
          {download.current_label && <span className="truncate text-xs text-muted">{download.current_label}</span>}
        </div>
        <EqMeter value={pct} className="mt-2 h-4 w-full" />
      </Link>,
    );
  }

  if (reviewCount > 0) {
    rows.push(
      <Link key="review" href="/wishlist" className="block transition-colors hover:bg-elevated">
        <span className="text-sm text-fg-strong">{t.dashboard.owToReview(reviewCount)}</span>
        {pending.length > 0 && (
          <span className="ml-3 text-xs text-muted">
            {pending.slice(0, 3).map((p) => [p.artist, p.title].filter(Boolean).join(" — ")).join(" · ")}
          </span>
        )}
      </Link>,
    );
  }

  if (inbox > 0) {
    rows.push(
      <Link key="inbox" href="/organize/files" className="block transition-colors hover:bg-elevated">
        <span className="text-sm text-fg-strong">{t.dashboard.owInbox(inbox)}</span>
      </Link>,
    );
  }

  if (leads.length > 0) {
    rows.push(
      <div key="leads">
        <div className="mb-1.5 flex items-baseline justify-between">
          <span className="text-[10px] uppercase tracking-wider text-muted">{t.dashboard.owLeads}</span>
          <Link href="/library" className="text-[10px] uppercase tracking-wider text-muted hover:text-fg">→</Link>
        </div>
        <ul>
          {leads.map((l) => (
            <li key={l.id}>
              <Link href={`/tracks/${l.id}`} className="flex items-baseline gap-3 py-1 transition-colors hover:bg-elevated">
                <span className="min-w-0 truncate text-sm text-fg">
                  {[l.artist, l.title].filter(Boolean).join(" — ")}
                </span>
                <Badge>{l.platform ?? l.source_type}</Badge>
                {l.added_at && <span className="tnum ml-auto shrink-0 text-[10px] text-faint">{fmtDate(l.added_at)}</span>}
              </Link>
            </li>
          ))}
        </ul>
      </div>,
    );
  }

  return (
    <section className="mt-6">
      <h2 className="mb-3 text-[10px] font-semibold uppercase tracking-wider text-fg-strong">{t.dashboard.openWork}</h2>
      {rows.length === 0 ? (
        <div className="border border-dashed border-border px-4 py-6 text-center text-sm text-muted">
          {t.dashboard.owNone}
        </div>
      ) : (
        <div className="divide-y divide-border border-y border-border">
          {rows.map((r, i) => (
            <Row key={i} n={i + 1}>{r}</Row>
          ))}
        </div>
      )}
    </section>
  );
}
```

Nota: `Badge` di `@/components/ui` ha `tone = "neutral"` di default, quindi `<Badge>` nudo rende già il badge neutro (`elevated` + `muted`). `downloadStatus` e `downloadPending` sono riesportati dal barrel `@/lib/api` (`export * from "./api/downloads"`).

- [ ] **Step 5: Verifica che passi**

Run: `cd frontend && npx vitest run tests/open-work.test.tsx`
Expected: PASS (6 test).

- [ ] **Step 6: Commit**

```bash
git add frontend/components/dashboard/open-work.tsx frontend/tests/open-work.test.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git commit -m "feat(dashboard): il banco «Lavoro aperto» — download vivo, revisioni, inbox, leads"
```

Stessa cautela del Task 2 sugli hunk i18n della sessione parallela (`git add -p` se necessario).

---

### Task 4: Frontespizio, assemblaggio pagina e polling

**Files:**
- Modify: `frontend/components/dashboard/figure.tsx`
- Modify: `frontend/app/page.tsx` (riscrittura del corpo)
- Modify: `frontend/lib/i18n/it.ts`, `frontend/lib/i18n/en.ts` (rimozione chiavi orfane)
- Delete: `frontend/components/dashboard/recent-list.tsx` (previa verifica consumer)
- Test: nessun test nuovo (la logica testabile vive nei Task 1–3); i test esistenti devono restare verdi.

**Interfaces:**
- Consumes: `Colophon` (Task 2), `OpenWork` + `queuesActive` (Task 3), `PipelineStrip` (invariato), `downloadStatus()`/`downloadPending()` da `@/lib/api`.
- Produces: la pagina `/` definitiva. `Figure` acquisisce la prop opzionale `big?: boolean` (cifra `text-4xl sm:text-5xl`).

- [ ] **Step 1: Frontespizio — prop `big` su Figure**

Sostituisci il contenuto di `frontend/components/dashboard/figure.tsx`:

```tsx
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

/** Cella hero: numero grande tabellare con etichetta maiuscola.
 *  `big` è il taglio da frontespizio della dashboard. */
export function Figure({ label, value, big = false }: { label: string; value: ReactNode; big?: boolean }) {
  return (
    <div className={cn("border-b border-r border-border", big ? "px-5 py-6" : "px-4 py-3.5")}>
      <div className="text-[10px] uppercase tracking-wider text-muted">{label}</div>
      <div className={cn("tnum mt-1 font-semibold tracking-tight text-fg-strong", big ? "text-4xl sm:text-5xl" : "text-3xl")}>
        {value}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Riscrivi il corpo di page.tsx**

Sostituisci il contenuto di `frontend/app/page.tsx` (partendo dallo stato attuale del working tree, che ha già perso la sezione gaps). Restano identici: gli stati `error`/`Loading`/empty, il fetch iniziale di stats/pipeline/labels/sets. Cambiano: niente playlist recenti (via `listImportedPlaylists`), nuovi fetch (leads, download, pending), polling condizionale, e il corpo frontespizio → pipeline → banco → colophon:

```tsx
"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Music, ArrowRight } from "lucide-react";
import {
  apiGet, getLabels, getPipeline, downloadStatus, downloadPending,
  type LibraryStats, type LabelStats, type SetlistSummary, type PipelineStatus,
  type DownloadStatus, type Track,
} from "@/lib/api";
import { useT } from "@/lib/i18n";
import { PipelineStrip } from "@/components/dashboard/pipeline";
import { Card, Alert, Loading } from "@/components/ui";
import { PageLayout } from "@/components/page-layout";
import { Figure } from "@/components/dashboard/figure";
import { Colophon } from "@/components/dashboard/colophon";
import { OpenWork, queuesActive } from "@/components/dashboard/open-work";

export default function Dashboard() {
  const t = useT();
  const [stats, setStats] = useState<LibraryStats | null>(null);
  const [labels, setLabels] = useState<LabelStats[]>([]);
  const [sets, setSets] = useState<SetlistSummary[] | null>(null);
  const [pipeline, setPipeline] = useState<PipelineStatus | null>(null);
  const [download, setDownload] = useState<DownloadStatus | null>(null);
  const [pending, setPending] = useState<Track[]>([]);
  const [leads, setLeads] = useState<Track[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    apiGet<LibraryStats>("/api/stats").then((s) => { setStats(s); setError(null); }).catch((e) => setError(String(e.message ?? e)));
    getPipeline().then(setPipeline).catch(() => setPipeline(null));
    getLabels().then(setLabels).catch(() => {});
    apiGet<SetlistSummary[]>("/api/sets").then(setSets).catch(() => setSets([]));
    downloadStatus().then(setDownload).catch(() => setDownload(null));
    downloadPending().then(setPending).catch(() => setPending([]));
    apiGet<{ total: number; items: Track[] }>("/api/tracks", {
      sort: "added_at", order: "desc", has_local_file: false, limit: 5,
    }).then((r) => setLeads(r.items)).catch(() => setLeads([]));
  }, []);
  useEffect(load, [load]);

  /* Vivo solo sulle code: finché un download gira, download e pipeline si
     riaggiornano; le cifre del frontespizio restano l'istantanea iniziale. */
  const active = queuesActive(download, pipeline);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => {
      downloadStatus().then(setDownload).catch(() => {});
      getPipeline().then(setPipeline).catch(() => {});
    }, 5000);
    return () => clearInterval(id);
  }, [active]);

  const empty = stats != null && stats.total_tracks === 0;

  return (
    <PageLayout>
      {error && <div className="mb-6"><Alert tone="danger">{t.dashboard.backendDown(error)}</Alert></div>}

      {!stats && !error && <Loading />}

      {empty && (
        <Card>
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <Music size={36} className="text-faint" />
            <div>
              <p className="font-medium text-fg-strong">{t.dashboard.emptyTitle}</p>
              <p className="mt-1 text-sm text-muted">{t.dashboard.emptyBody}</p>
            </div>
            <Link href="/playlists" className="inline-flex items-center gap-1.5 bg-fg-strong px-4 py-2 text-xs font-medium uppercase tracking-wider text-bg transition-colors hover:bg-fg">
              {t.dashboard.importPlaylist} <ArrowRight size={14} />
            </Link>
          </div>
        </Card>
      )}

      {stats && !empty && (
        <>
          {/* Frontespizio: le quattro misure come apertura tipografica. */}
          <div className="grid grid-cols-2 border-l border-t border-border sm:grid-cols-4">
            <Figure big label={t.dashboard.figureDiscovered} value={stats.total_tracks} />
            <Figure
              big
              label={t.dashboard.figureOwned}
              value={(
                <>
                  {stats.with_local_file}
                  {stats.total_tracks > 0 && (
                    <span className="ml-2 text-sm font-normal text-muted">
                      {Math.round((stats.with_local_file / stats.total_tracks) * 100)}%
                    </span>
                  )}
                </>
              )}
            />
            <Figure big label={t.dashboard.figurePlaylists} value={stats.playlists} />
            <Figure big label={t.dashboard.figureSets} value={sets ? sets.length : "—"} />
          </div>

          {/* Striscia di orientamento: le fasi del ciclo con contatori vivi. */}
          {pipeline && (
            <div className="mt-6">
              <PipelineStrip p={pipeline} />
            </div>
          )}

          {/* Il banco: lavoro aperto sulla catena di acquisizione. */}
          <OpenWork download={download} pending={pending} inboxFiles={pipeline?.inbox_files ?? null} leads={leads} />

          {/* Il colophon: il ritratto della libreria in righe tipografiche. */}
          <Colophon stats={stats} labels={labels} />
        </>
      )}
    </PageLayout>
  );
}
```

Nota — la striscia pipeline oggi sta sopra le figure; nel Registro va **sotto il frontespizio** come da spec. Verifica di non aver lasciato il vecchio blocco `{!empty && pipeline && …}` in testa.

- [ ] **Step 3: Rimuovi recent-list e le chiavi i18n orfane**

Prima verifica i consumer (il wrapper grep del sistema è ugrep: pattern semplici, niente `^` dentro alternanze):

```bash
grep -rn "recent-list" frontend --include="*.tsx" --include="*.ts" -l
grep -rn "RecentList" frontend --include="*.tsx" -l
```

Se l'unico consumer era `app/page.tsx` (atteso): `rm frontend/components/dashboard/recent-list.tsx`. `mini-bars.tsx` RESTA (lo usano le pagine labels); `histogram.tsx` resta (colophon + eventuali altri usi).

Poi, per ciascuna di queste chiavi `dashboard.*`, `grep -rn "<chiave>" frontend --include="*.tsx" --include="*.ts"` e rimuovila da **entrambi** i dizionari solo se l'unico uso residuo è il dizionario stesso: `libraryShape`, `bpmHistogram`, `topKeys`, `recentActivity`, `recentSets`, `noSetsYet`, `recentPlaylistsHeading`, `noPlaylistsYet`, `catalog`, `topGenres`, `topLabels`, `viewAllMasculine`, `viewAllFeminine`, `tracksAbbrev`. Attenzione: `trackCount` resta (lo usa `Histogram` full). `listImportedPlaylists` in `lib/api` resta (lo usano altre pagine).

- [ ] **Step 4: Verifica completa**

```bash
cd frontend && npx vitest run && npm run lint
```

Expected: tutti i test PASS (compresi quelli dei Task 1–3 e i preesistenti), lint pulito. Se un test preesistente citava la vecchia dashboard, aggiornalo coerentemente con il Registro (non cancellarlo senza capire cosa proteggeva).

- [ ] **Step 5: Commit**

```bash
git add frontend/app/page.tsx frontend/components/dashboard/figure.tsx frontend/lib/i18n/it.ts frontend/lib/i18n/en.ts
git rm frontend/components/dashboard/recent-list.tsx
git commit -m "feat(dashboard): «Il Registro» — frontespizio, banco, colophon al posto delle tre colonne"
```

(Stessa cautela sugli hunk paralleli in i18n e `page.tsx`: committare solo il proprio lavoro.)

---

### Task 5: Verifica finale (build, temi, responsive)

**Files:** nessuna modifica prevista; correzioni eventuali sui file dei task precedenti.

**Interfaces:**
- Consumes: tutto il lavoro dei Task 1–4.
- Produces: prova che la pagina funziona nell'app reale, su entrambi i temi.

- [ ] **Step 1: Build di produzione**

```bash
cd frontend && npm run build
```

Expected: build verde, nessun errore di tipo.

- [ ] **Step 2: Verifica visiva nel browser**

Con il backend attivo su :8000 e il dev server (riusare quello dell'utente su :3000 se già acceso — vedi memoria di progetto; altrimenti preview via launch.json):

1. Aprire `/`: frontespizio → pipeline → banco → colophon nell'ordine.
2. Tema dark E paper (toggle in nav): entrambi leggibili, nessun colore fuori token.
3. Viewport stretto (`sm`): frontespizio 2×2, righe colophon che vanno a capo, banco a piena larghezza.
4. Console browser senza errori.
5. Se possibile, avviare un download da `/wishlist` e verificare che la riga «Download in corso» compaia con l'EqMeter che avanza, e che sparisca (col polling che si spegne) a coda ferma.

- [ ] **Step 3: Screenshot di prova per l'utente**

Screenshot della pagina nei due temi da condividere in chat come prova.

- [ ] **Step 4: Commit di eventuali correzioni**

Solo se la verifica ha richiesto ritocchi; stessi vincoli di staging dei task precedenti.
