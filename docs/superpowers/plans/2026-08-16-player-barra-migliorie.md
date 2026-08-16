# Player: barra, controlli custom, continuità, Media Session — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** trasformare il player docked d'angolo in una barra a tutta larghezza con trasporto custom (seek, prev/next), continuità d'ascolto con auto-avanzamento sulle tracce possedute e integrazione Media Session.

**Architecture:** tutto frontend. Il provider (`lib/player.tsx`) guadagna un contesto d'ascolto (snapshot della lista di provenienza) con `next`/`prev`. Un nuovo componente `PlayerTransport` incapsula l'elemento `<audio>` nascosto e i controlli custom, inclusa la Media Session. `DockedPlayer` diventa la barra a tre zone che compone tutto. `TrackPlayButton` accetta una prop `context` che i call site con una lista passano.

**Tech Stack:** Next.js 16 (App Router), React 19, Tailwind, vitest + @testing-library/react (jsdom), lucide-react.

**Spec:** `docs/superpowers/specs/2026-08-16-player-barra-migliorie-design.md`.

## Global Constraints

- Nessuna modifica backend: `GET /api/tracks/{id}/audio` risponde già 206 alle Range request.
- Vietato (CLAUDE.md): waveform, cue point, coda manuale in stile deck. Fuori scope della spec: volume nel dock, scorciatoie tastiera in-app, loop/shuffle, persistenza posizione.
- I `data-testid` esistenti restano invariati: `local-audio`, `preview-audio`, `preview-iframe`.
- Auto-avanzamento SOLO per sorgenti `local-track`; le preview discovery restano una alla volta. Errore audio = stop con messaggio, MAI salto alla traccia dopo.
- Ogni testo user-facing va in ENTRAMBI i dizionari (`lib/i18n/it.ts` e `lib/i18n/en.ts`).
- Frontend Next.js 16: leggere `frontend/CLAUDE.md`; qui non si tocca il routing.
- Worktree senza `node_modules`: serve un `npm install` reale (il symlink rompe Turbopack).
- Tutti i comandi partono da `frontend/` del worktree: `/Users/lucadenegri/Develop/DJProject01/.claude/worktrees/audio-player-improvements-ba875a/frontend`.
- I test esistenti (`tests/player.test.tsx`, `tests/track-play-button.test.tsx`, `tests/docked-player-rating.test.tsx`) devono restare verdi senza modifiche, salvo dove un task li estende esplicitamente.

---

### Task 1: Contesto d'ascolto nel provider

**Files:**
- Modify: `frontend/lib/player.tsx`
- Test (create): `frontend/tests/player-context.test.tsx`

**Interfaces:**
- Consumes: `LocalTrack`, `PlaybackSource`, `usePlayer` esistenti in `lib/player.tsx`.
- Produces (usati dai Task 3 e 5):
  - `play(source: PlaybackSource, context?: LocalTrack[]): void` — secondo parametro nuovo, opzionale.
  - `next(): void`, `prev(): void` — suonano la traccia adiacente mantenendo il contesto; no-op ai bordi.
  - `hasNext: boolean`, `hasPrev: boolean`.

- [ ] **Step 0: npm install nel worktree**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/audio-player-improvements-ba875a/frontend
npm install
```

Expected: `node_modules` creato senza errori.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `frontend/tests/player-context.test.tsx`:

```tsx
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  discoveryPreview: vi.fn(() => new Promise(() => {})), // pending: basta a montare la preview
  trackCoverSrc: () => null,
  trackAudioUrl: (id: number) => `/api/tracks/${id}/audio`,
  discoverySaveForLater: vi.fn(),
  updateTrack: vi.fn(),
}));

import { PlayerProvider, usePlayer, type LocalTrack } from "@/lib/player";

const LIST: LocalTrack[] = [
  { id: 1, title: "One", artist: "A" },
  { id: 2, title: "Two", artist: "A" },
  { id: 3, title: "Three", artist: "A" },
];

function Harness() {
  const p = usePlayer();
  return (
    <div>
      <button onClick={() => p.play({ kind: "local-track", track: LIST[0] }, LIST)}>play-first</button>
      <button onClick={() => p.play({ kind: "local-track", track: LIST[1] }, LIST)}>play-mid</button>
      <button onClick={() => p.play({ kind: "local-track", track: { id: 9, title: "Solo", artist: "B" } })}>play-solo</button>
      <button onClick={() => p.play({ kind: "discovery-preview", item: { key: "x", artist: "Ar", title: "Ti", sourceId: "1", source: "discogs", level: "track", label: "Ti" } })}>play-preview</button>
      <button onClick={() => p.next()}>next</button>
      <button onClick={() => p.prev()}>prev</button>
      <span data-testid="active-id">{p.active?.kind === "local-track" ? p.active.track.id : "-"}</span>
      <span data-testid="has-next">{String(p.hasNext)}</span>
      <span data-testid="has-prev">{String(p.hasPrev)}</span>
    </div>
  );
}

function renderHarness() {
  return render(
    <PlayerProvider>
      <Harness />
    </PlayerProvider>,
  );
}

const click = async (label: string) =>
  act(async () => {
    screen.getByText(label).click();
  });

describe("contesto d'ascolto", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("in mezzo alla lista: prev e next disponibili", async () => {
    renderHarness();
    await click("play-mid");
    expect(screen.getByTestId("active-id").textContent).toBe("2");
    expect(screen.getByTestId("has-prev").textContent).toBe("true");
    expect(screen.getByTestId("has-next").textContent).toBe("true");
  });

  it("next avanza mantenendo il contesto; a fine lista si ferma", async () => {
    renderHarness();
    await click("play-mid");
    await click("next");
    expect(screen.getByTestId("active-id").textContent).toBe("3");
    expect(screen.getByTestId("has-prev").textContent).toBe("true");
    expect(screen.getByTestId("has-next").textContent).toBe("false");
    await click("next"); // no-op al bordo
    expect(screen.getByTestId("active-id").textContent).toBe("3");
  });

  it("prev torna indietro; all'inizio si ferma", async () => {
    renderHarness();
    await click("play-mid");
    await click("prev");
    expect(screen.getByTestId("active-id").textContent).toBe("1");
    expect(screen.getByTestId("has-prev").textContent).toBe("false");
    await click("prev"); // no-op al bordo
    expect(screen.getByTestId("active-id").textContent).toBe("1");
  });

  it("un play senza contesto azzera il contesto", async () => {
    renderHarness();
    await click("play-mid");
    await click("play-solo");
    expect(screen.getByTestId("active-id").textContent).toBe("9");
    expect(screen.getByTestId("has-prev").textContent).toBe("false");
    expect(screen.getByTestId("has-next").textContent).toBe("false");
  });

  it("una preview discovery azzera il contesto", async () => {
    renderHarness();
    await click("play-mid");
    await click("play-preview");
    expect(screen.getByTestId("has-prev").textContent).toBe("false");
    expect(screen.getByTestId("has-next").textContent).toBe("false");
    // tornare a una locale senza contesto non lo resuscita
    await click("play-solo");
    expect(screen.getByTestId("has-next").textContent).toBe("false");
  });

  it("un contesto vuoto equivale a nessun contesto", async () => {
    function EmptyCtx() {
      const p = usePlayer();
      return (
        <div>
          <button onClick={() => p.play({ kind: "local-track", track: LIST[0] }, [])}>play-empty</button>
          <span data-testid="empty-next">{String(p.hasNext)}</span>
        </div>
      );
    }
    render(
      <PlayerProvider>
        <EmptyCtx />
      </PlayerProvider>,
    );
    await act(async () => {
      screen.getByText("play-empty").click();
    });
    expect(screen.getByTestId("empty-next").textContent).toBe("false");
  });
});
```

- [ ] **Step 2: Verificare che fallisca**

```bash
npx vitest run tests/player-context.test.tsx
```

Expected: FAIL — `p.next is not a function` (o proprietà `hasNext` undefined → textContent "undefined").

- [ ] **Step 3: Implementare il contesto in `lib/player.tsx`**

Nel tipo `Ctx`, sostituire la firma di `play` e aggiungere i campi nuovi:

```tsx
type Ctx = {
  active: PlaybackSource | null;
  status: Status;
  data: DiscoveryPreview | null;
  /** Vero solo quando dall'app esce davvero del suono. `status` dice cosa è
   *  caricato nel dock, non se sta suonando: in pausa resta "playing". Lo
   *  alimenta il dock con gli eventi play/pause/ended dell'elemento audio; la
   *  Home ci attacca l'animazione della consolle. */
  audible: boolean;
  /** `context` è lo snapshot ordinato della lista di provenienza (solo tracce
   *  possedute): abilita prev/next e l'auto-avanzamento. Assente = niente
   *  continuità. Snapshot, non riferimento vivo: filtri successivi della lista
   *  non toccano l'ascolto in corso. */
  play: (source: PlaybackSource, context?: LocalTrack[]) => void;
  stop: () => void;
  /** Riservato al dock: pubblica lo stato reale dell'elemento audio. */
  setAudible: (v: boolean) => void;
  hasPrev: boolean;
  hasNext: boolean;
  prev: () => void;
  next: () => void;
};
```

Nel `PlayerProvider`:

```tsx
export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const [active, setActive] = useState<PlaybackSource | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [data, setData] = useState<DiscoveryPreview | null>(null);
  const [elementPlaying, setAudible] = useState(false);
  const [context, setContext] = useState<LocalTrack[] | null>(null);
  const reqId = useRef(0);

  const play = useCallback((source: PlaybackSource, ctx?: LocalTrack[]) => {
    const id = ++reqId.current; // invalida qualunque risoluzione preview in volo
    setActive(source);
    setData(null);
    setAudible(false); // la nuova sorgente è muta finché il suo elemento non parte
    if (source.kind === "local-track") {
      // Snapshot del contesto: presente solo se non vuoto. Un play senza
      // contesto azzera quello precedente (l'ascolto continuo riparte solo
      // da una lista).
      setContext(ctx && ctx.length > 0 ? ctx : null);
      setStatus("playing"); // stream diretto: nessuna risoluzione async
      return;
    }
    setContext(null); // le preview discovery si valutano una alla volta
    // ... (il resto del ramo discovery-preview resta IDENTICO a com'è oggi)
  }, []);

  const stop = useCallback(() => {
    reqId.current++;
    setActive(null);
    setStatus("idle");
    setData(null);
    setAudible(false);
    setContext(null);
  }, []);

  // Posizione nel contesto, derivata dall'id attivo: se la traccia attiva non
  // viene dal contesto (o non c'è contesto) l'indice è -1 e prev/next spariscono.
  const idx =
    context && active?.kind === "local-track"
      ? context.findIndex((tr) => tr.id === active.track.id)
      : -1;
  const hasPrev = idx > 0;
  const hasNext = idx >= 0 && context != null && idx < context.length - 1;

  const next = useCallback(() => {
    if (context && idx >= 0 && idx < context.length - 1) {
      play({ kind: "local-track", track: context[idx + 1] }, context);
    }
  }, [context, idx, play]);

  const prev = useCallback(() => {
    if (context && idx > 0) {
      play({ kind: "local-track", track: context[idx - 1] }, context);
    }
  }, [context, idx, play]);

  /* L'iframe YouTube non espone eventi senza caricare la sua API: quando è
     montato sta suonando in autoplay, quindi lo si conta come audibile. */
  const audible = elementPlaying || (status === "playing" && data?.kind === "youtube");

  return (
    <PlayerCtx.Provider value={{ active, status, data, audible, play, stop, setAudible, hasPrev, hasNext, prev, next }}>
      {children}
    </PlayerCtx.Provider>
  );
}
```

Il ramo discovery-preview dentro `play` (risoluzione `discoveryPreview`, gestione `streamUrl` Bandcamp, guardia `id !== reqId.current`) non cambia di una virgola: solo il `setContext(null)` in testa al ramo è nuovo.

- [ ] **Step 4: Verificare che passi, insieme ai test esistenti del player**

```bash
npx vitest run tests/player-context.test.tsx tests/player.test.tsx tests/track-play-button.test.tsx tests/docked-player-rating.test.tsx
```

Expected: PASS tutti (la firma di `play` è retrocompatibile).

- [ ] **Step 5: Commit**

```bash
git add lib/player.tsx tests/player-context.test.tsx
git commit -m "feat(player): contesto d'ascolto nel provider — prev/next su snapshot della lista"
```

---

### Task 2: Componente PlayerTransport (trasporto custom)

**Files:**
- Create: `frontend/components/player-transport.tsx`
- Modify: `frontend/lib/i18n/it.ts` (blocco `player`, ~riga 818)
- Modify: `frontend/lib/i18n/en.ts` (blocco `player`, ~riga 818)
- Test (create): `frontend/tests/player-transport.test.tsx`

**Interfaces:**
- Consumes: `useT` da `@/lib/i18n`; icone `Pause, Play, SkipBack, SkipForward` da lucide-react.
- Produces (usato dal Task 3):

```tsx
export type TransportPrevNext = {
  hasPrev: boolean;
  hasNext: boolean;
  onPrev: () => void;
  onNext: () => void;
};

export function PlayerTransport(props: {
  src: string;
  testId: string;                       // "local-audio" | "preview-audio"
  onAudible: (v: boolean) => void;      // eventi reali play/pause/ended
  onEnded?: () => void;
  onError?: () => void;
  prevNext?: TransportPrevNext | null;  // presente solo con contesto
  mediaMeta?: { title: string; artist: string; artworkUrl: string | null } | null; // usato dal Task 4
}): JSX.Element;
```

- [ ] **Step 1: Aggiungere le stringhe i18n**

In `lib/i18n/it.ts`, blocco `player`:

```ts
  player: {
    play: "Ascolta",
    pause: "Pausa",
    stop: "Ferma",
    previous: "Traccia precedente",
    next: "Traccia successiva",
    seek: "Posizione",
    close: "Chiudi player",
    unsupportedFormat: "Formato non riproducibile nel browser",
  },
```

In `lib/i18n/en.ts`, stesso blocco:

```ts
  player: {
    play: "Play",
    pause: "Pause",
    stop: "Stop",
    previous: "Previous track",
    next: "Next track",
    seek: "Seek",
    close: "Close player",
    unsupportedFormat: "Format not playable in the browser",
  },
```

- [ ] **Step 2: Scrivere il test che fallisce**

Creare `frontend/tests/player-transport.test.tsx`:

```tsx
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlayerTransport } from "@/components/player-transport";

/* jsdom non implementa play()/pause(): i mock simulano l'elemento reale
   dispacciando gli eventi corrispondenti, così il componente reagisce come
   nel browser. */
beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("pause"));
  });
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function renderTransport(extra: Partial<Parameters<typeof PlayerTransport>[0]> = {}) {
  const onAudible = vi.fn();
  const utils = render(
    <PlayerTransport src="/api/tracks/5/audio" testId="local-audio" onAudible={onAudible} {...extra} />,
  );
  return { onAudible, audio: screen.getByTestId("local-audio") as HTMLAudioElement, ...utils };
}

/** La durata in jsdom è NaN: la si finge come farebbe il browser a metadata caricati. */
function setDuration(audio: HTMLAudioElement, v: number) {
  Object.defineProperty(audio, "duration", { configurable: true, get: () => v });
  fireEvent.durationChange(audio);
}

describe("PlayerTransport", () => {
  it("senza durata: tempi a riposo e seek disabilitato", () => {
    renderTransport();
    expect(screen.getByText("0:00")).toBeTruthy();
    expect(screen.getByText("–:––")).toBeTruthy();
    expect((screen.getByLabelText("Posizione") as HTMLInputElement).disabled).toBe(true);
  });

  it("mostra durata e posizione formattate mm:ss", () => {
    const { audio } = renderTransport();
    setDuration(audio, 187);
    expect(screen.getByText("3:07")).toBeTruthy();
    Object.defineProperty(audio, "currentTime", { configurable: true, value: 65, writable: true });
    fireEvent.timeUpdate(audio);
    expect(screen.getByText("1:05")).toBeTruthy();
  });

  it("il seek imposta currentTime sull'elemento", () => {
    const { audio } = renderTransport();
    setDuration(audio, 200);
    let ct = 0;
    Object.defineProperty(audio, "currentTime", { configurable: true, get: () => ct, set: (v) => { ct = v; } });
    fireEvent.change(screen.getByLabelText("Posizione"), { target: { value: "30" } });
    expect(ct).toBe(30);
  });

  it("play/pause: il bottone comanda l'elemento e riflette lo stato reale", async () => {
    const { audio, onAudible } = renderTransport();
    await act(async () => {
      fireEvent.play(audio); // autoplay partito
    });
    expect(onAudible).toHaveBeenLastCalledWith(true);
    const btn = screen.getByLabelText("Pausa");
    await act(async () => {
      btn.click();
    });
    expect(onAudible).toHaveBeenLastCalledWith(false);
    expect(screen.getByLabelText("Ascolta")).toBeTruthy(); // tornato "play"
    await act(async () => {
      screen.getByLabelText("Ascolta").click();
    });
    expect(onAudible).toHaveBeenLastCalledWith(true);
  });

  it("ended: pubblica il silenzio e chiama onEnded", async () => {
    const onEnded = vi.fn();
    const { audio, onAudible } = renderTransport({ onEnded });
    await act(async () => {
      fireEvent.play(audio);
      fireEvent.ended(audio);
    });
    expect(onAudible).toHaveBeenLastCalledWith(false);
    expect(onEnded).toHaveBeenCalledOnce();
  });

  it("error: chiama onError", () => {
    const onError = vi.fn();
    const { audio } = renderTransport({ onError });
    fireEvent.error(audio);
    expect(onError).toHaveBeenCalledOnce();
  });

  it("prev/next: assenti senza contesto, presenti e cablati con contesto", async () => {
    renderTransport();
    expect(screen.queryByLabelText("Traccia successiva")).toBeNull();
    cleanup();
    const onPrev = vi.fn();
    const onNext = vi.fn();
    renderTransport({ prevNext: { hasPrev: false, hasNext: true, onPrev, onNext } });
    const prevBtn = screen.getByLabelText("Traccia precedente") as HTMLButtonElement;
    expect(prevBtn.disabled).toBe(true);
    await act(async () => {
      screen.getByLabelText("Traccia successiva").click();
    });
    expect(onNext).toHaveBeenCalledOnce();
    expect(onPrev).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: Verificare che fallisca**

```bash
npx vitest run tests/player-transport.test.tsx
```

Expected: FAIL — modulo `@/components/player-transport` inesistente.

- [ ] **Step 4: Implementare il componente**

Creare `frontend/components/player-transport.tsx`:

```tsx
"use client";

import { useRef, useState } from "react";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";

import { useT } from "@/lib/i18n";

export type TransportPrevNext = {
  hasPrev: boolean;
  hasNext: boolean;
  onPrev: () => void;
  onNext: () => void;
};

type Props = {
  src: string;
  testId: string;
  /** Pubblica gli eventi reali dell'elemento (play/pause/ended): alimenta `audible`. */
  onAudible: (v: boolean) => void;
  onEnded?: () => void;
  onError?: () => void;
  /** Presente solo quando c'è un contesto d'ascolto: mostra prev/next. */
  prevNext?: TransportPrevNext | null;
  /** Metadata per il Now Playing di sistema (Media Session). */
  mediaMeta?: { title: string; artist: string; artworkUrl: string | null } | null;
};

/** mm:ss per il trasporto: a differenza di fmtDuration niente "—", a riposo 0:00. */
function fmtTime(s: number): string {
  if (!Number.isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, "0")}`;
}

/** Trasporto custom sul motore <audio> nascosto: play/pause, prev/next (solo con
 *  contesto), seek con tempi. Riusato identico per traccia locale, clip iTunes e
 *  stream Bandcamp; l'iframe YouTube non passa di qui. */
export function PlayerTransport({ src, testId, onAudible, onEnded, onError, prevNext, mediaMeta }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [paused, setPaused] = useState(true);
  const [position, setPosition] = useState(0);
  const [duration, setDuration] = useState(0);
  const t = useT();

  // Stream senza durata nota (metadata non ancora arrivati, o live): il seek
  // non ha senso e resta disabilitato.
  const seekable = Number.isFinite(duration) && duration > 0;

  const toggle = () => {
    const el = audioRef.current;
    if (!el) return;
    if (el.paused) void el.play();
    else el.pause();
  };

  return (
    <div className="flex w-full items-center gap-3">
      {prevNext && (
        <button
          type="button"
          aria-label={t.player.previous}
          disabled={!prevNext.hasPrev}
          onClick={prevNext.onPrev}
          className="shrink-0 text-faint transition-colors hover:text-fg disabled:opacity-40 disabled:hover:text-faint"
        >
          <SkipBack size={15} />
        </button>
      )}
      <button
        type="button"
        aria-label={paused ? t.player.play : t.player.pause}
        onClick={toggle}
        className="shrink-0 text-fg transition-colors hover:text-fg-strong"
      >
        {paused ? <Play size={17} /> : <Pause size={17} />}
      </button>
      {prevNext && (
        <button
          type="button"
          aria-label={t.player.next}
          disabled={!prevNext.hasNext}
          onClick={prevNext.onNext}
          className="shrink-0 text-faint transition-colors hover:text-fg disabled:opacity-40 disabled:hover:text-faint"
        >
          <SkipForward size={15} />
        </button>
      )}
      <span className="tnum shrink-0 text-[11px] text-faint">{fmtTime(position)}</span>
      <input
        type="range"
        aria-label={t.player.seek}
        min={0}
        max={seekable ? duration : 0}
        step={0.1}
        value={seekable ? Math.min(position, duration) : 0}
        disabled={!seekable}
        onChange={(e) => {
          const el = audioRef.current;
          if (!el) return;
          const v = Number(e.target.value);
          el.currentTime = v;
          setPosition(v);
        }}
        className="h-1 min-w-0 flex-1 cursor-pointer appearance-none bg-border text-fg accent-current disabled:cursor-default"
      />
      <span className="tnum shrink-0 text-[11px] text-faint">{seekable ? fmtTime(duration) : "–:––"}</span>
      <audio
        ref={audioRef}
        data-testid={testId}
        src={src}
        autoPlay
        onPlay={() => {
          setPaused(false);
          onAudible(true);
        }}
        onPause={() => {
          setPaused(true);
          onAudible(false);
        }}
        onEnded={() => {
          setPaused(true);
          onAudible(false);
          onEnded?.();
        }}
        onError={() => onError?.()}
        onTimeUpdate={(e) => setPosition(e.currentTarget.currentTime)}
        onDurationChange={(e) => setDuration(e.currentTarget.duration)}
        className="hidden"
      />
    </div>
  );
}
```

Nota: `mediaMeta` è dichiarato ma volutamente non ancora usato — lo consuma il Task 4. Se ESLint segnala il parametro inutilizzato, ometterlo dalla destrutturazione mantenendolo nel tipo `Props`.

- [ ] **Step 5: Verificare che passi**

```bash
npx vitest run tests/player-transport.test.tsx
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add components/player-transport.tsx tests/player-transport.test.tsx lib/i18n/it.ts lib/i18n/en.ts
git commit -m "feat(player): trasporto custom — play/pause, prev/next, seek con tempi"
```

---

### Task 3: Barra a tutta larghezza

**Files:**
- Modify: `frontend/components/docked-player.tsx` (riscrittura del layout)
- Modify: `frontend/components/editorial-shell.tsx` (padding-bottom sul `<main>`)
- Test (create): `frontend/tests/docked-player-bar.test.tsx`

**Interfaces:**
- Consumes: `PlayerTransport`, `TransportPrevNext` (Task 2); `hasPrev/hasNext/prev/next` dal provider (Task 1).
- Produces: CSS var globale `--player-bar-height` (px, "0px" a player chiuso), consumata da `editorial-shell.tsx`. I `data-testid` restano `local-audio`/`preview-audio`/`preview-iframe`.

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `frontend/tests/docked-player-bar.test.tsx`:

```tsx
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  discoveryPreview: vi.fn(),
  trackCoverSrc: () => null,
  trackAudioUrl: (id: number) => `/api/tracks/${id}/audio`,
  discoverySaveForLater: vi.fn(),
  updateTrack: vi.fn(),
}));

import { DockedPlayer } from "@/components/docked-player";
import { PlayerProvider, usePlayer, type LocalTrack } from "@/lib/player";

const LIST: LocalTrack[] = [
  { id: 5, title: "First", artist: "A" },
  { id: 6, title: "Second", artist: "A" },
];

function Harness() {
  const p = usePlayer();
  return (
    <div>
      <button onClick={() => p.play({ kind: "local-track", track: LIST[0] }, LIST)}>play-ctx</button>
      <button onClick={() => p.play({ kind: "local-track", track: LIST[0] })}>play-solo</button>
      <span data-testid="active-id">{p.active?.kind === "local-track" ? p.active.track.id : "-"}</span>
    </div>
  );
}

function renderAll() {
  return render(
    <PlayerProvider>
      <Harness />
      <DockedPlayer />
    </PlayerProvider>,
  );
}

describe("barra player", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(cleanup);

  it("con contesto: a fine traccia avanza alla successiva", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-ctx").click();
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/5/audio");
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("active-id").textContent).toBe("6");
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/6/audio");
  });

  it("senza contesto: a fine traccia si ferma sulla stessa", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-solo").click();
    });
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("active-id").textContent).toBe("5");
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/5/audio");
  });

  it("errore audio: messaggio, NIENTE salto alla traccia dopo", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-ctx").click();
    });
    await act(async () => {
      fireEvent.error(screen.getByTestId("local-audio"));
    });
    // il salto a catena maschererebbe file rotti: si resta sull'errore
    expect(screen.getByTestId("active-id").textContent).toBe("5");
    expect(screen.queryByTestId("local-audio")).toBeNull();
    expect(screen.getByText(/browser/i)).toBeTruthy();
  });

  it("prev/next del trasporto cablati al provider", async () => {
    renderAll();
    await act(async () => {
      screen.getByText("play-ctx").click();
    });
    await act(async () => {
      screen.getByLabelText("Traccia successiva").click();
    });
    expect(screen.getByTestId("active-id").textContent).toBe("6");
    await act(async () => {
      screen.getByLabelText("Traccia precedente").click();
    });
    expect(screen.getByTestId("active-id").textContent).toBe("5");
  });

  it("a player chiuso la CSS var dell'altezza torna a 0px", async () => {
    const { unmount } = renderAll();
    await act(async () => {
      screen.getByText("play-ctx").click();
    });
    unmount();
    expect(document.documentElement.style.getPropertyValue("--player-bar-height")).toBe("0px");
  });
});
```

(Niente asserzione sull'altezza a barra aperta: in jsdom `offsetHeight` è sempre 0, il valore non sarebbe significativo.)

- [ ] **Step 2: Verificare che fallisca**

```bash
npx vitest run tests/docked-player-bar.test.tsx
```

Expected: FAIL — `getByLabelText("Traccia successiva")` non trovato (il dock attuale usa `<audio controls>` senza trasporto) e auto-avanzamento assente.

- [ ] **Step 3: Riscrivere `components/docked-player.tsx`**

Contenuto completo del file dopo la modifica:

```tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, Plus, X } from "lucide-react";

import { discoverySaveForLater, trackAudioUrl } from "@/lib/api";
import { PlayerTransport } from "@/components/player-transport";
import { RatingDiamond } from "@/components/rating-diamond";
import { TrackCover } from "@/components/track-cover";
import { useT } from "@/lib/i18n";
import { usePlayer } from "@/lib/player";

export function DockedPlayer() {
  const { active, status, data, stop, setAudible, hasPrev, hasNext, prev, next } = usePlayer();
  const t = useT();
  // Stati effimeri del dock: errore di riproduzione locale (formato non
  // supportato / file sparito) e stato dell'azione ADD per la preview discovery.
  // Niente useEffect: l'azzeramento al cambio sorgente avviene "durante il
  // render" (pattern React consigliato per derivare stato da un prop che
  // cambia), evitando il render extra di un setState sincrono dentro un effect.
  const [localError, setLocalError] = useState(false);
  const [savingAdd, setSavingAdd] = useState(false);
  const [addedKey, setAddedKey] = useState<string | null>(null);

  const activeLocalId = active?.kind === "local-track" ? active.track.id : null;
  const activePreviewKey = active?.kind === "discovery-preview" ? active.item.key : null;
  const activeKey = active
    ? active.kind === "local-track"
      ? `l:${activeLocalId}`
      : `p:${activePreviewKey}`
    : null;
  const [prevKey, setPrevKey] = useState(activeKey);
  if (activeKey !== prevKey) {
    setPrevKey(activeKey);
    setLocalError(false);
    setSavingAdd(false);
  }

  const visible = !!active && status !== "idle";
  const barRef = useRef<HTMLDivElement>(null);

  // Altezza pubblicata in --player-bar-height (pattern di --jobs-bar-height):
  // editorial-shell la usa come padding-bottom del <main>, così l'ultima riga
  // delle liste non resta coperta dalla barra. Senza deps: il contenuto della
  // barra (trasporto/messaggi/video) ne cambia l'altezza tra un render e l'altro.
  useEffect(() => {
    const h = visible ? (barRef.current?.offsetHeight ?? 0) : 0;
    document.documentElement.style.setProperty("--player-bar-height", `${h}px`);
  });
  useEffect(
    () => () => {
      document.documentElement.style.setProperty("--player-bar-height", "0px");
    },
    [],
  );

  const prevNext = useMemo(
    () => (hasPrev || hasNext ? { hasPrev, hasNext, onPrev: prev, onNext: next } : null),
    [hasPrev, hasNext, prev, next],
  );

  // Metadata per il Now Playing di sistema (consumati dal trasporto, Task 4).
  const mediaMeta = useMemo(() => {
    if (!active) return null;
    return active.kind === "local-track"
      ? { title: active.track.title, artist: active.track.artist, artworkUrl: active.track.albumArtUrl ?? null }
      : { title: active.item.title, artist: active.item.artist, artworkUrl: active.item.addInput?.album_art_url ?? null };
  }, [active]);

  if (!active || status === "idle") return null;

  const title = active.kind === "local-track" ? active.track.title : active.item.title;
  const artist = active.kind === "local-track" ? active.track.artist : active.item.artist;

  // Miniatura: per la traccia posseduta l'artwork Spotify o la cover embedded
  // (via TrackCover); per la preview discovery la thumb del lead. `key` rimonta
  // TrackCover al cambio sorgente, azzerando il suo stato di fallback.
  const coverArt =
    active.kind === "local-track"
      ? { id: active.track.id, album_art_url: active.track.albumArtUrl ?? null, has_local_file: true }
      : { id: 0, album_art_url: active.item.addInput?.album_art_url ?? null, has_local_file: false };

  const addInput = active.kind === "discovery-preview" ? active.item.addInput : undefined;
  const isAdded = addedKey != null && addedKey === activePreviewKey;
  const onAdd = async () => {
    if (!addInput || !activePreviewKey || savingAdd || isAdded) return;
    setSavingAdd(true);
    try {
      await discoverySaveForLater(addInput);
      setAddedKey(activePreviewKey);
    } catch {
      // Silenzioso: l'utente può ritentare (l'errore non blocca l'ascolto).
    } finally {
      setSavingAdd(false);
    }
  };

  return (
    // `bottom` dinamico: se la barra job globale è visibile pubblica la sua
    // altezza in `--jobs-bar-height`, così la barra player le sta sopra invece
    // di sovrapporsi; senza barra job il fallback 0px la tiene sul fondo.
    <div
      ref={barRef}
      style={{ bottom: "var(--jobs-bar-height, 0px)" }}
      className="fixed inset-x-0 z-[60] border-t border-border-strong bg-surface"
    >
      {/* Il video YouTube non sta in una barra orizzontale: riquadro compatto
          ancorato sopra la barra, a destra, con i controlli dell'iframe.
          Condizioni inline (non un boolean precalcolato): TypeScript narra
          `active` e `data` solo dentro la catena di guardie. */}
      {active.kind === "discovery-preview" && status === "playing" && data?.kind === "youtube" && data.youtube_video_id && (
        <div className="absolute bottom-full right-4 mb-2 w-64 max-w-[calc(100vw-2rem)] border border-border-strong bg-surface">
          <div className="aspect-video w-full overflow-hidden">
            <iframe
              data-testid="preview-iframe"
              className="h-full w-full"
              src={`https://www.youtube-nocookie.com/embed/${data.youtube_video_id}?autoplay=1`}
              title={active.item.title}
              allow="autoplay; encrypted-media"
              allowFullScreen
            />
          </div>
        </div>
      )}

      <div className="flex items-center gap-3 px-3 py-2 sm:gap-4 sm:px-4 sm:py-2.5">
        {/* Zona sinistra: cover, titolo/artista, rating. */}
        <div className="flex w-44 min-w-0 shrink-0 items-center gap-2.5 sm:w-64">
          <TrackCover key={activeKey ?? "x"} track={coverArt} className="h-10 w-10 sm:h-14 sm:w-14" iconSize={18} />
          <div className="min-w-0">
            <div className="truncate text-sm text-fg">{title}</div>
            <div className="truncate text-xs text-faint">{artist}</div>
          </div>
          {active.kind === "local-track" && (
            <RatingDiamond trackId={active.track.id} rating={active.track.rating ?? null} />
          )}
        </div>

        {/* Zona centro: trasporto (o messaggi di stato). Larghezza massima
            contenuta: su schermi larghi il binario di seek non diventa
            chilometrico. YouTube non ha trasporto: audio e controlli stanno
            nell'iframe sopra la barra. */}
        <div className="flex min-w-0 flex-1 justify-center">
          <div className="w-full max-w-2xl">
            {active.kind === "local-track" &&
              (localError ? (
                <div className="text-xs text-faint">{t.player.unsupportedFormat}</div>
              ) : (
                <PlayerTransport
                  key={activeKey ?? "x"}
                  src={trackAudioUrl(active.track.id)}
                  testId="local-audio"
                  onAudible={setAudible}
                  onEnded={() => {
                    if (hasNext) next();
                  }}
                  onError={() => {
                    setLocalError(true);
                    setAudible(false);
                  }}
                  prevNext={prevNext}
                  mediaMeta={mediaMeta}
                />
              ))}
            {active.kind === "discovery-preview" && (
              <>
                {status === "loading" && <div className="text-xs text-faint">{t.discovery.previewLoading}</div>}
                {status === "unavailable" && <div className="text-xs text-faint">{t.discovery.noPreview}</div>}
                {status === "playing" && data?.kind === "itunes" && data.audio_url && (
                  <PlayerTransport
                    key={activeKey ?? "x"}
                    src={data.audio_url}
                    testId="preview-audio"
                    onAudible={setAudible}
                    mediaMeta={mediaMeta}
                  />
                )}
              </>
            )}
          </div>
        </div>

        {/* Zona destra: ADD per i lead discovery, chiudi. */}
        <div className="flex shrink-0 items-center gap-1">
          {addInput && (
            <button
              type="button"
              onClick={onAdd}
              disabled={savingAdd || isAdded}
              aria-label={t.discovery.add}
              className="flex items-center gap-1 border border-border-strong px-1.5 py-0.5 text-[11px] uppercase tracking-wider text-faint transition-colors hover:text-fg disabled:opacity-60"
            >
              {isAdded ? <Check size={13} /> : <Plus size={12} />}
              <span className="hidden sm:inline">{t.discovery.add}</span>
            </button>
          )}
          <button aria-label={t.player.close} onClick={stop} className="p-1 text-faint hover:text-fg">
            <X size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
```

Differenze rilevanti rispetto a oggi, per chi rilegge il diff: sparisce `audioEvents` (gli eventi vivono nel trasporto), sparisce `<audio controls>`, l'iframe YouTube esce dal flusso e diventa riquadro ancorato, la barra passa da `w-80` d'angolo a `inset-x-0` con `border-t`.

- [ ] **Step 4: Padding delle pagine in `components/editorial-shell.tsx`**

Sostituire la riga del `<main>`:

```tsx
        <main className="min-w-0" style={{ paddingBottom: "var(--player-bar-height, 0px)" }}>{children}</main>
```

- [ ] **Step 5: Verificare i test nuovi e TUTTI gli esistenti del player**

```bash
npx vitest run tests/docked-player-bar.test.tsx tests/player.test.tsx tests/track-play-button.test.tsx tests/docked-player-rating.test.tsx tests/player-transport.test.tsx tests/player-context.test.tsx
```

Expected: PASS tutti. In particolare `tests/player.test.tsx` (testid e flusso eventi invariati) e `tests/track-play-button.test.tsx` (messaggio errore invariato) NON vanno modificati: se falliscono è un bug della barra, non dei test.

- [ ] **Step 6: Verifica visiva nel browser**

Avviare il dev server (o riusare quello dell'utente su :3000 se già attivo) e con il Browser pane: aprire la libreria, premere play su una traccia posseduta, verificare barra in fondo a tutta larghezza, seek funzionante, prev/next, ultima riga della lista raggiungibile (padding), convivenza con la barra job se presente. Da una pagina Discovery provare una preview (audio e, se capita, YouTube nel riquadro).

- [ ] **Step 7: Commit**

```bash
git add components/docked-player.tsx components/editorial-shell.tsx tests/docked-player-bar.test.tsx
git commit -m "feat(player): barra a tutta larghezza con trasporto custom e auto-avanzamento"
```

---

### Task 4: Media Session

**Files:**
- Modify: `frontend/components/player-transport.tsx`
- Test (create): `frontend/tests/media-session.test.tsx`

**Interfaces:**
- Consumes: props `mediaMeta` e `prevNext` già dichiarate nel Task 2.
- Produces: nessuna API nuova — effetto collaterale su `navigator.mediaSession` (metadata + handler `play`/`pause` sempre, `previoustrack`/`nexttrack` solo con contesto; tutto azzerato allo smontaggio).

- [ ] **Step 1: Scrivere il test che fallisce**

Creare `frontend/tests/media-session.test.tsx`:

```tsx
import { cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PlayerTransport } from "@/components/player-transport";

/* jsdom non ha né mediaSession né MediaMetadata: stub minimi. */
class FakeMediaMetadata {
  constructor(public init: { title?: string; artist?: string; artwork?: { src: string }[] }) {}
}

type Handler = (() => void) | null;

function installMediaSession() {
  const handlers = new Map<string, Handler>();
  const ms = {
    metadata: null as FakeMediaMetadata | null,
    setActionHandler: vi.fn((action: string, h: Handler) => handlers.set(action, h)),
  };
  Object.defineProperty(navigator, "mediaSession", { configurable: true, value: ms });
  vi.stubGlobal("MediaMetadata", FakeMediaMetadata);
  return { ms, handlers };
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  // @ts-expect-error: rimozione dello stub per il test successivo
  delete navigator.mediaSession;
});

beforeEach(() => {
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("play"));
    return Promise.resolve();
  });
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(function (this: HTMLMediaElement) {
    this.dispatchEvent(new Event("pause"));
  });
});

const META = { title: "Acid Trip", artist: "Artist", artworkUrl: "http://art" };

describe("Media Session", () => {
  it("pubblica i metadata e gli handler play/pause", () => {
    const { ms, handlers } = installMediaSession();
    render(<PlayerTransport src="/a" testId="local-audio" onAudible={() => {}} mediaMeta={META} />);
    const meta = ms.metadata as FakeMediaMetadata;
    expect(meta.init.title).toBe("Acid Trip");
    expect(meta.init.artist).toBe("Artist");
    expect(meta.init.artwork).toEqual([{ src: "http://art" }]);
    expect(typeof handlers.get("play")).toBe("function");
    expect(typeof handlers.get("pause")).toBe("function");
    // senza contesto, prev/next sono esplicitamente rimossi
    expect(handlers.get("previoustrack")).toBeNull();
    expect(handlers.get("nexttrack")).toBeNull();
  });

  it("con contesto registra previoustrack/nexttrack sui bordi disponibili", () => {
    const { handlers } = installMediaSession();
    const onPrev = vi.fn();
    const onNext = vi.fn();
    render(
      <PlayerTransport
        src="/a"
        testId="local-audio"
        onAudible={() => {}}
        mediaMeta={META}
        prevNext={{ hasPrev: false, hasNext: true, onPrev, onNext }}
      />,
    );
    expect(handlers.get("previoustrack")).toBeNull(); // bordo: prima traccia
    handlers.get("nexttrack")?.();
    expect(onNext).toHaveBeenCalledOnce();
  });

  it("l'handler play comanda l'elemento audio", () => {
    const { handlers } = installMediaSession();
    render(<PlayerTransport src="/a" testId="local-audio" onAudible={() => {}} mediaMeta={META} />);
    handlers.get("play")?.();
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it("allo smontaggio azzera metadata e handler", () => {
    const { ms, handlers } = installMediaSession();
    const { unmount } = render(
      <PlayerTransport src="/a" testId="local-audio" onAudible={() => {}} mediaMeta={META} />,
    );
    unmount();
    expect(ms.metadata).toBeNull();
    expect(handlers.get("play")).toBeNull();
    expect(handlers.get("pause")).toBeNull();
  });

  it("senza navigator.mediaSession non esplode", () => {
    expect(() =>
      render(<PlayerTransport src="/a" testId="local-audio" onAudible={() => {}} mediaMeta={META} />),
    ).not.toThrow();
  });
});
```

- [ ] **Step 2: Verificare che fallisca**

```bash
npx vitest run tests/media-session.test.tsx
```

Expected: FAIL — `ms.metadata` resta `null`, nessun `setActionHandler` chiamato (solo l'ultimo test passa).

- [ ] **Step 3: Implementare l'effetto in `player-transport.tsx`**

Aggiungere `useEffect` all'import di react, poi dentro `PlayerTransport` (dopo gli `useState`, prima del `return`):

```tsx
  // Now Playing di sistema: metadata e comandi remoti (tasti multimediali,
  // lock screen). Feature facoltativa: dove mediaSession/MediaMetadata mancano
  // (browser vecchi, jsdom) non succede nulla. prev/next registrati solo con
  // contesto e solo verso i bordi disponibili; allo smontaggio si azzera tutto
  // per non lasciare comandi appesi a un elemento morto.
  useEffect(() => {
    if (!("mediaSession" in navigator) || typeof MediaMetadata === "undefined") return;
    const ms = navigator.mediaSession;
    ms.metadata = new MediaMetadata({
      title: mediaMeta?.title ?? "",
      artist: mediaMeta?.artist ?? "",
      artwork: mediaMeta?.artworkUrl ? [{ src: mediaMeta.artworkUrl }] : [],
    });
    ms.setActionHandler("play", () => void audioRef.current?.play());
    ms.setActionHandler("pause", () => audioRef.current?.pause());
    ms.setActionHandler("previoustrack", prevNext?.hasPrev ? () => prevNext.onPrev() : null);
    ms.setActionHandler("nexttrack", prevNext?.hasNext ? () => prevNext.onNext() : null);
    return () => {
      ms.metadata = null;
      ms.setActionHandler("play", null);
      ms.setActionHandler("pause", null);
      ms.setActionHandler("previoustrack", null);
      ms.setActionHandler("nexttrack", null);
    };
  }, [mediaMeta, prevNext]);
```

(`mediaMeta` e `prevNext` arrivano memoizzati dal dock — Task 3 — quindi l'effetto non gira a ogni render.)

- [ ] **Step 4: Verificare che passi, con la suite del player**

```bash
npx vitest run tests/media-session.test.tsx tests/player-transport.test.tsx tests/docked-player-bar.test.tsx tests/player.test.tsx
```

Expected: PASS tutti.

- [ ] **Step 5: Commit**

```bash
git add components/player-transport.tsx tests/media-session.test.tsx
git commit -m "feat(player): Media Session — tasti multimediali e Now Playing di sistema"
```

---

### Task 5: Prop `context` su TrackPlayButton e call site

**Files:**
- Modify: `frontend/components/track-play-button.tsx`
- Modify: `frontend/components/library-track-grid.tsx`
- Modify: `frontend/app/sets/[id]/page.tsx:406`
- Test (modify): `frontend/tests/track-play-button.test.tsx`

**Interfaces:**
- Consumes: `play(source, context?)` dal Task 1; `LocalTrack` da `@/lib/player`.
- Produces: `TrackPlayButton` accetta `context?: PlayableRow[]` (stesso shape della prop `track`); i call site con una lista la passano.

- [ ] **Step 1: Estendere il test (che fallisce)**

In `frontend/tests/track-play-button.test.tsx` aggiungere in coda al `describe` esistente (la funzione `renderButton` esistente resta invariata):

```tsx
  const CTX = [
    { id: 5, title: "T", artist: "A", has_local_file: true },
    { id: 6, title: "U", artist: "A", has_local_file: true },
    { id: 7, title: "V", artist: "A", has_local_file: false }, // non posseduta: esclusa dal contesto
  ];

  function renderWithContext() {
    return render(
      <PlayerProvider>
        <TrackPlayButton track={CTX[0]} context={CTX} />
        <DockedPlayer />
      </PlayerProvider>,
    );
  }

  it("con contesto: a fine traccia avanza alla successiva posseduta", async () => {
    renderWithContext();
    await act(async () => {
      screen.getByRole("button").click();
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/5/audio");
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/6/audio");
  });

  it("il contesto salta le tracce non possedute: dopo la 6 non c'è una next", async () => {
    renderWithContext();
    await act(async () => {
      screen.getByRole("button").click();
    });
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    // id 7 non ha file: il contesto filtrato finisce con la 6
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/6/audio");
  });

  it("senza contesto: a fine traccia non avanza", async () => {
    renderButton({ id: 5, title: "T", artist: "A", has_local_file: true });
    await act(async () => {
      screen.getByRole("button").click();
    });
    await act(async () => {
      fireEvent.ended(screen.getByTestId("local-audio"));
    });
    expect(screen.getByTestId("local-audio").getAttribute("src")).toBe("/api/tracks/5/audio");
  });
```

Nota: questo test file oggi NON mocka `@/lib/api` — se il render della barra (Task 3) lo richiede già oggi il file passa senza mock perché `trackAudioUrl` reale produce `/api/tracks/{id}/audio`; lasciare com'è.

- [ ] **Step 2: Verificare che fallisca**

```bash
npx vitest run tests/track-play-button.test.tsx
```

Expected: FAIL sui due test col contesto (TypeScript/prop inesistente o nessun avanzamento); il test "senza contesto" passa già.

- [ ] **Step 3: Implementare la prop**

Contenuto completo di `frontend/components/track-play-button.tsx` dopo la modifica:

```tsx
"use client";

import { Pause, Play } from "lucide-react";

import { useT } from "@/lib/i18n";
import { usePlayer, type LocalTrack } from "@/lib/player";

type PlayableRow = {
  id: number;
  title: string | null;
  artist: string | null;
  has_local_file?: boolean | null;
  album_art_url?: string | null;
  rating?: number | null;
};

type Props = {
  track: PlayableRow;
  /** Lista ordinata da cui parte l'ascolto (griglia libreria, set): abilita
   *  prev/next e auto-avanzamento nel player. Viene filtrata alle possedute e
   *  passata come snapshot. */
  context?: PlayableRow[];
  className?: string;
};

function toLocal(tr: PlayableRow): LocalTrack {
  return {
    id: tr.id,
    title: tr.title ?? "",
    artist: tr.artist ?? "",
    albumArtUrl: tr.album_art_url ?? null,
    rating: tr.rating ?? null,
  };
}

/** Play/pausa dell'audizione rapida di una traccia posseduta. Non renderizza
 *  nulla se la traccia non ha un file locale. Riusabile in ogni riga-traccia. */
export function TrackPlayButton({ track, context, className }: Props) {
  const player = usePlayer();
  const t = useT();
  if (!track.has_local_file) return null;

  const isActive = player.active?.kind === "local-track" && player.active.track.id === track.id;

  const toggle = (e: React.MouseEvent) => {
    e.stopPropagation(); // non attivare la navigazione della riga
    if (isActive) {
      player.stop();
    } else {
      const ctx = context?.filter((tr) => tr.has_local_file).map(toLocal);
      player.play({ kind: "local-track", track: toLocal(track) }, ctx);
    }
  };

  return (
    <button
      type="button"
      aria-label={isActive ? t.player.stop : t.player.play}
      onClick={toggle}
      className={className ?? "shrink-0 text-faint transition-colors hover:text-fg"}
    >
      {isActive ? <Pause size={14} /> : <Play size={14} />}
    </button>
  );
}
```

- [ ] **Step 4: Passare il contesto dai call site**

`frontend/components/library-track-grid.tsx` — la card riceve la lista intera:

```tsx
      {tracks.map((tr) => (
        <LibraryTrackCard key={tr.id} track={tr} context={tracks} onEdit={onEdit} trackLinkQuery={trackLinkQuery} />
      ))}
```

```tsx
function LibraryTrackCard({ track, context, onEdit, trackLinkQuery }: { track: Track; context: Track[]; onEdit: (t: Track) => void; trackLinkQuery: string }) {
```

e nel JSX della card:

```tsx
      <TrackPlayButton
        track={track}
        context={context}
        className="absolute left-1 top-1 rounded-full bg-black/60 p-1.5 text-white opacity-0 transition hover:bg-black/80 focus-visible:opacity-100 group-hover:opacity-100"
      />
```

`frontend/app/sets/[id]/page.tsx` riga 406 — il loop mappa `setlist.tracks` (già in ordine di posizione):

```tsx
                  <TrackPlayButton track={st.track} context={setlist.tracks.map((s) => s.track)} className="px-1 text-faint hover:text-fg" />
```

Gli altri call site (`track-state-icons.tsx`, `app/tracks/[id]/page.tsx`) restano senza contesto, di proposito: righe fuori da una lista d'ascolto.

- [ ] **Step 5: Verificare che passi**

```bash
npx vitest run tests/track-play-button.test.tsx tests/docked-player-bar.test.tsx tests/player-context.test.tsx
```

Expected: PASS tutti.

- [ ] **Step 6: Commit**

```bash
git add components/track-play-button.tsx components/library-track-grid.tsx "app/sets/[id]/page.tsx" tests/track-play-button.test.tsx
git commit -m "feat(player): le liste passano il contesto d'ascolto al play"
```

---

### Task 6: Verifica completa e documentazione

**Files:**
- Modify: `README.md` (~riga 22)
- Modify: `PROGRESS.md` (~riga 15)
- Modify: `docs/ROADMAP.md` (~riga 17-19)

**Interfaces:** nessuna — chiusura: suite completa, lint, build, allineamento docs.

- [ ] **Step 1: Suite frontend completa**

```bash
npx vitest run
```

Expected: PASS tutti (nessun test preesistente rotto).

- [ ] **Step 2: Lint e build**

```bash
npm run lint
npm run build
```

Expected: lint pulito; build Turbopack completata senza errori (richiede il `node_modules` reale del Task 1 Step 0).

- [ ] **Step 3: Allineare le tre menzioni del player nei docs**

`README.md` (~riga 22), sostituire la frase:

```text
  audio hash. Owned tracks play in-app, read-only, through a shared docked player — for a
  quick audition, not for mixing.
```

con:

```text
  audio hash. Owned tracks play in-app, read-only, through a shared bottom player bar
  (custom transport with seek, prev/next over the originating list, auto-advance on
  owned tracks, OS media keys via Media Session) — for a quick audition, not for mixing.
```

`PROGRESS.md` (~riga 15), sostituire:

```text
  the shared docked player.
```

con:

```text
  the shared bottom player bar (custom transport with seek, prev/next over the
  originating list, auto-advance on owned tracks, OS Media Session).
```

`docs/ROADMAP.md` (~riga 17-19), sostituire:

```text
  acquisition). Owned tracks are playable, read-only, one at a time, through a shared
  docked player (`GET /api/tracks/{id}/audio`) — playback never touches the file or
  its tags.
```

con:

```text
  acquisition). Owned tracks are playable, read-only, one at a time, through a shared
  bottom player bar (`GET /api/tracks/{id}/audio`; custom transport with seek,
  prev/next over the originating list, auto-advance on owned tracks, Media Session) —
  playback never touches the file or its tags.
```

- [ ] **Step 4: Commit finale**

```bash
cd /Users/lucadenegri/Develop/DJProject01/.claude/worktrees/audio-player-improvements-ba875a
git add README.md PROGRESS.md docs/ROADMAP.md
git commit -m "docs: il player docked diventa barra — trasporto custom, continuità, Media Session"
```
