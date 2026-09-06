# Analisi BPM/key automatica a fine Apply — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** quando l'Apply di un piano Organize ha applicato qualcosa, l'app deve avviare da sola l'analisi BPM/key sulle tracce che ne sono prive, subito dopo la scansione che l'Apply già innesca.

**Architecture:** modifica di solo frontend, dentro `JobsProvider`. Esiste già un anello `apply (done, applied_ops > 0) → scan`; si aggiunge un terzo anello `scan (done, se innescato dall'apply) → startAnalysis("missing")`. L'innesco è un `useRef` booleano armato solo quando la scansione post-apply è stata accettata dal backend e consumato al primo fronte `running → done|error` del job di scansione, così una scansione manuale non lo eredita mai. Nessun endpoint nuovo, nessun tipo nuovo, backend intoccato.

**Tech Stack:** Next.js 16 (App Router), React 19, TypeScript, Vitest + Testing Library con timer finti.

Spec di riferimento: `docs/superpowers/specs/2026-09-06-analisi-bpm-key-post-apply-design.md`.

## Global Constraints

- **Il backend non cambia di una riga.** Nessun file sotto `backend/` va toccato da questo piano.
- **Nessuna API nuova sulla `JobsApi`.** La catena è un comportamento interno al provider, non una funzione esposta ai consumatori: non aggiungere campi al context.
- **`scope` dell'analisi automatica: sempre `"missing"`.** Mai `"all"`.
- **Errori dell'avvio ingoiati in silenzio** (`.catch(() => {})` con commento che dice quali sono), come già fa l'anello `apply → scan`: Essentia assente (503), analisi già in corso (409), backend offline.
- **Commenti in italiano**, come tutto il resto di `jobs-provider.tsx`; il commento deve dire *perché* la catena esiste e *perché* l'analisi va dopo la scansione, non cosa fa il codice.
- **Nessun `setState` nei nuovi effetti.** L'innesco è un `useRef`: cambia fuori dal ciclo di render.
- **Comandi frontend** dalla cartella `frontend/`: `npx vitest run <file>` per un singolo file, `npm run lint`, `npm run build`.
- **Nessun `Co-Authored-By` nei commit.**

---

### Task 1: il terzo anello nel provider, con i suoi test

**Files:**
- Modify: `frontend/components/jobs-provider.tsx` (import da `@/lib/api` in cima; nuovo `useRef` e nuovo `useEffect` accanto all'anello esistente, oggi alle righe 325-339)
- Test: `frontend/tests/jobs-provider-organize.test.tsx` (aggiunta di mock e di cinque casi)
- Modify: `frontend/tests/jobs-provider.test.tsx` (solo il mock di `@/lib/api`, vedi Step 1)

**Interfaces:**
- Consumes: `startAnalysis(scope: "missing" | "all", trackIds?: number[]) => Promise<AnalysisJobStatus>` da `@/lib/api` (definita in `frontend/lib/api/analysis.ts`, già esistente); `startScan(locations?: Location[]) => Promise<void>` interna al provider; lo stato `libraryIndex: LibraryIndexJob | null`, il cui `status` è `"idle" | "running" | "done" | "error"`.
- Produces: nessuna interfaccia pubblica. Il solo effetto osservabile è la chiamata a `startAnalysis("missing")`.

- [ ] **Step 1: rendere i due test file dei job capaci di reggere il nuovo import**

`jobs-provider.tsx` importerà `startAnalysis` da `@/lib/api`. I due soli file di test che montano `JobsProvider` sostituiscono quel modulo con una factory: se l'export non c'è nella factory, Vitest fallisce con `No "startAnalysis" export is defined on the "@/lib/api" mock` appena il provider viene importato. Vanno aggiornati **prima**, altrimenti il test del passo successivo fallisce per il motivo sbagliato.

In `frontend/tests/jobs-provider-organize.test.tsx`, aggiungere la spia accanto alle altre (dopo la riga `const startScan = vi.fn(async () => idleApply);`):

```tsx
const startAnalysis = vi.fn(async () => ({
  status: "running" as const, processed: 0, total: 0, analyzed: 0, failed: 0,
  applied: 0, current_label: null, error: null,
}));
```

e nella factory di `vi.mock("@/lib/api", ...)` aggiungere la riga:

```tsx
  startAnalysis: (...a: unknown[]) => startAnalysis(...(a as [])),
```

In `frontend/tests/jobs-provider.test.tsx`, nella factory di `vi.mock("@/lib/api", ...)`, aggiungere:

```tsx
  startAnalysis: vi.fn(),
```

- [ ] **Step 2: verificare che i test esistenti passino ancora**

```bash
cd frontend && npx vitest run tests/jobs-provider.test.tsx tests/jobs-provider-organize.test.tsx
```

Atteso: PASS su entrambi i file. Se qui è già rosso, il problema non è tuo: fermati e segnalalo.

- [ ] **Step 3: scrivere i due test che falliscono (il caso positivo e il suo negativo)**

In `frontend/tests/jobs-provider-organize.test.tsx`, dentro il `describe("job Organize nel provider unico", ...)`, dopo il test `"ma NON riparte se l'apply non ha applicato nulla"`.

Serve prima un aiuto locale, perché la catena ha tre anelli e ogni test deve poterla percorrere. Aggiungerlo appena sopra il `describe`:

```tsx
/** Percorre la catena apply → scan: apply in corso, poi concluso con `ops`
 *  operazioni applicate. Lascia il job di scansione fermo su idle. */
async function applyConcluso(ops: number) {
  applyStatus.mockResolvedValue({ ...idleApply, status: "running", processed: 1, total: 3 });
  render(<JobsProvider><div /></JobsProvider>);
  await tick();
  applyStatus.mockResolvedValue({
    ...idleApply, status: "done", processed: 3, total: 3,
    result: { applied_ops: ops } as ApplyJobState["result"],
  });
  await tick(2000);
}

/** Porta il job di scansione da running all'esito indicato, un poll per stato. */
async function scansione(esito: "done" | "error") {
  libraryIndexStatus.mockResolvedValue({ ...idleLibraryIndex, status: "running", processed: 1, total: 2 });
  await tick(2000);
  libraryIndexStatus.mockResolvedValue({ ...idleLibraryIndex, status: esito });
  await tick(2000);
}
```

E i due test:

```tsx
  it("a fine scansione innescata dall'apply parte l'analisi BPM/key", async () => {
    /* Terzo anello: apply → scan → analisi. Sta DOPO la scansione perché
       l'apply sposta i file senza riscrivere i percorsi in DB. */
    await applyConcluso(3);
    expect(startScan).toHaveBeenCalledTimes(1);
    expect(startAnalysis).not.toHaveBeenCalled();

    await scansione("done");

    expect(startAnalysis).toHaveBeenCalledTimes(1);
    expect(startAnalysis).toHaveBeenCalledWith("missing");
  });

  it("ma una scansione manuale NON fa partire l'analisi", async () => {
    /* Il caso che distingue questo anello da un innesco incondizionato su
       ogni fine scansione: senza, l'analisi ripartirebbe a ogni scan. */
    render(<JobsProvider><div /></JobsProvider>);
    await tick();

    await scansione("done");

    expect(startAnalysis).not.toHaveBeenCalled();
  });
```

- [ ] **Step 4: eseguire i test e vederli fallire**

```bash
cd frontend && npx vitest run tests/jobs-provider-organize.test.tsx
```

Atteso: FAIL sul primo dei due nuovi test, con `expected "spy" to be called 1 times, but got 0 times`. Il secondo passa già (nessuno chiama ancora `startAnalysis`): è normale, è il guardiano che serve al passo dopo.

- [ ] **Step 5: implementare l'anello**

In `frontend/components/jobs-provider.tsx`, aggiungere `startAnalysis` all'import esistente da `@/lib/api` (la lista di import nominali in cima al file, quella che contiene già `analysisStatus`), lasciando gli import di tipo dove sono:

```tsx
import {
  analysisStatus, downloadStatus, generateStatus, libraryIndexStatus, shazamIdentifyStatus,
  startAnalysis, streamingImportStatus,
  type AnalysisJobStatus, type DownloadStatus, type GenStatus, type LibraryIndexJob, type ShazamIdentifyState,
  type StreamingImportJobStatus,
} from "@/lib/api";
```

Poi, subito **sopra** il blocco commentato `/* Riavvio automatico della scansione a fine Apply. ... */`, dichiarare l'innesco:

```tsx
  /* Innesco del terzo anello. Vive in un ref e non in uno stato: cambia fuori
     dal ciclo di render e non deve provocarne uno. */
  const analysisAfterScan = useRef(false);
```

Nell'effetto esistente dell'anello `apply → scan`, armare l'innesco solo quando il backend ha davvero accettato la scansione:

```tsx
    if (was === "running" && apply.status === "done" && (apply.result?.applied_ops ?? 0) > 0) {
      startScan()
        .then(() => { analysisAfterScan.current = true; })
        .catch(() => { /* backend offline o scan già in corso (409) */ });
    }
```

E subito dopo quell'effetto, il terzo anello:

```tsx
  /* Terzo anello: a fine scansione parte l'analisi BPM/key sulle tracce che ne
     sono prive. Perché dopo la scansione e non a fine Apply: l'apply sposta e
     rinomina i file senza riscrivere `AudioFile.path` né `Track.local_path`, ed
     è la scansione a riallinearli. Lanciarla prima passerebbe a Essentia
     percorsi che non esistono più, e il job segna `analyzed_at` anche quando la
     decodifica fallisce: il buco resterebbe, mascherato da traccia analizzata.
     L'innesco si consuma al primo esito della scansione qualunque esso sia, così
     una scansione manuale successiva non se lo ritrova addosso. */
  const scanStatus = libraryIndex?.status;
  const prevScanStatus = useRef<LibraryIndexJob["status"] | undefined>(scanStatus);
  useEffect(() => {
    const was = prevScanStatus.current;
    prevScanStatus.current = scanStatus;
    if (was !== "running" || (scanStatus !== "done" && scanStatus !== "error")) return;
    const armed = analysisAfterScan.current;
    analysisAfterScan.current = false;
    if (armed && scanStatus === "done") {
      startAnalysis("missing")
        .then(() => { refresh(); })
        .catch(() => { /* Essentia assente (503), analisi già in corso (409), rete */ });
    }
  }, [scanStatus, refresh]);
```

- [ ] **Step 6: eseguire i test e vederli passare**

```bash
cd frontend && npx vitest run tests/jobs-provider-organize.test.tsx
```

Atteso: PASS, sei test in tutto (i quattro preesistenti più i due nuovi).

- [ ] **Step 7: provare che le asserzioni misurino davvero qualcosa**

Non è un passo formale: è il modo di scoprire un test vacuo prima che entri in repo.

1. Commentare la riga `.then(() => { analysisAfterScan.current = true; })` (lasciando la `startScan()`): il test `"a fine scansione innescata dall'apply parte l'analisi BPM/key"` deve diventare **rosso**. Ripristinare.
2. Sostituire `if (armed && scanStatus === "done")` con `if (scanStatus === "done")`: il test `"ma una scansione manuale NON fa partire l'analisi"` deve diventare **rosso**. Ripristinare.

Se una delle due rotture lascia tutto verde, il test corrispondente non sta misurando il comportamento: sistemarlo prima di proseguire.

- [ ] **Step 8: aggiungere i tre casi che restano**

Nello stesso `describe`, dopo i due test già scritti:

```tsx
  it("se la scansione viene rifiutata l'analisi non parte", async () => {
    /* Scan già in corso (409) o backend offline: l'innesco non si arma, e la
       scansione che sta girando non è quella che riallinea i file appena
       spostati. */
    startScan.mockRejectedValueOnce(new Error("409 scan_running"));
    await applyConcluso(3);
    expect(startScan).toHaveBeenCalledTimes(1);

    await scansione("done");

    expect(startAnalysis).not.toHaveBeenCalled();
  });

  it("una scansione finita in errore consuma comunque l'innesco", async () => {
    /* Niente analisi su un indice non riallineato; e l'innesco non deve
       sopravvivere per aggrapparsi alla prima scansione manuale successiva. */
    await applyConcluso(3);

    await scansione("error");
    expect(startAnalysis).not.toHaveBeenCalled();

    await scansione("done");
    expect(startAnalysis).not.toHaveBeenCalled();
  });

  it("un avvio dell'analisi rifiutato non rompe la barra dei job", async () => {
    /* Essentia non installato (503): l'apply è concluso e riuscito, l'errore
       dell'anello opzionale non deve arrivare all'utente né alla barra. */
    startAnalysis.mockRejectedValueOnce(new Error("503 analysis_engine_unavailable"));
    await applyConcluso(3);
    await scansione("done");

    expect(startAnalysis).toHaveBeenCalledTimes(1);

    applyStatus.mockResolvedValue({ ...idleApply, status: "running", processed: 2, total: 8 });
    await tick(2000);
    expect(screen.getByText("25%")).toBeTruthy();
  });
```

Attenzione a `mockRejectedValueOnce` su `startAnalysis`: il `vi.clearAllMocks()` dell'`afterEach` azzera le chiamate ma **non** ripristina l'implementazione di default della spia. Qui va bene perché sono `...Once` e vengono consumati dentro il loro test; non convertirli in `mockRejectedValue` senza `Once`.

- [ ] **Step 9: eseguire tutti i test dei job**

```bash
cd frontend && npx vitest run tests/jobs-provider.test.tsx tests/jobs-provider-organize.test.tsx tests/jobs-provider-unico.test.tsx
```

Atteso: PASS su tutti e tre i file, nove test nel file Organize.

- [ ] **Step 10: lint e build**

```bash
cd frontend && npm run lint
```

Atteso: nessun errore. In particolare nessun `react-hooks/exhaustive-deps` sul nuovo effetto: le dipendenze sono `[scanStatus, refresh]` e i ref non vanno dichiarati.

```bash
cd frontend && npm run build
```

Atteso: build completata.

- [ ] **Step 11: commit**

```bash
git add frontend/components/jobs-provider.tsx frontend/tests/jobs-provider-organize.test.tsx frontend/tests/jobs-provider.test.tsx
git commit -m "feat(jobs): l'analisi BPM/key riparte da sola a fine Apply"
```

---

### Task 2: la suite completa e la documentazione

**Files:**
- Modify: `PROGRESS.md` (sezione `## Current state by area`, in testa all'elenco datato)
- Test: nessun test nuovo; qui si esegue la suite intera

- [ ] **Step 1: eseguire l'intera suite unitaria del frontend**

```bash
cd frontend && npm run test:unit
```

Atteso: PASS. Se un file estraneo alla catena fallisce, verificare se era già rosso prima del Task 1 con `git stash`; un rosso preesistente non è tuo, ma va segnalato invece che nascosto.

- [ ] **Step 2: eseguire la suite backend, per prova che non è stata toccata**

```bash
cd backend && source .venv/bin/activate && python -m pytest tests -q
```

Atteso: PASS. Questo piano non modifica il backend: un rosso qui è preesistente e va segnalato, non aggiustato dentro questo lavoro.

- [ ] **Step 3: scrivere la voce in PROGRESS.md**

In `PROGRESS.md`, come **primo elemento** dell'elenco sotto `## Current state by area` (cioè prima della voce `- **I comandi massivi di Issues agiscono su ciò che vedi** (2026-09-04)`), inserire:

```markdown
- **L'analisi BPM/key riparte da sola a fine Apply** (2026-09-06): applicare un
  piano Organize lascia tracce possedute senza BPM né key, e finora toccava
  ricordarsi di aprire `/analysis` e premere Avvia. Ora la catena ha tre anelli:
  `apply (con operazioni applicate) → scan → analisi con scope "missing"`.
  L'analisi sta **dopo** la scansione, non a fine apply, perché `apply_plan`
  sposta e rinomina i file senza riscrivere `AudioFile.path` né
  `Track.local_path`: è la scansione a riallinearli, e analizzare prima
  passerebbe a Essentia percorsi morti valorizzando comunque `analyzed_at`, cioè
  mascherando il buco invece di riempirlo. L'innesco vive in un ref del
  `JobsProvider`, si arma solo se la scansione post-apply è stata accettata e si
  consuma al primo esito della scansione, così una scansione manuale non lo
  eredita mai. I valori entrano nei canonici solo via `auto_apply_missing`, che
  riempie i campi vuoti con provenienza `cratory`: la gerarchia
  `manual > rekordbox > cratory` resta intatta.
```

- [ ] **Step 4: rileggere il diff della documentazione**

```bash
git diff PROGRESS.md
```

Atteso: una sola voce aggiunta, nessuna riga preesistente modificata.

- [ ] **Step 5: commit**

```bash
git add PROGRESS.md
git commit -m "docs: l'analisi BPM/key automatica a fine Apply nel PROGRESS"
```

---

## Verifica finale (facoltativa, richiede la libreria vera)

Non è un passo di test automatico: è il modo di vedere la catena in funzione, se sull'ambiente c'è un piano applicabile e Essentia installato.

1. Avviare backend e frontend (`uvicorn app.main:app --reload --port 8000`, `npm run dev`).
2. Aprire `/organize/plan`, costruire un piano, applicarlo.
3. Guardare la barra dei job in basso: deve comparire prima la riga dell'Apply, poi quella della scansione, poi quella dell'analisi audio.
4. Aprire `/analysis` e controllare che il conteggio delle tracce senza BPM/key sia calato.
