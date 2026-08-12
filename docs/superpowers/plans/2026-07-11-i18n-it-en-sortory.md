# i18n IT/EN Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Sortory bilingue IT/EN — UI frontend ed errori backend seguono un'impostazione lingua persistente, con default inglese.

**Architecture:** Dizionario TypeScript fatto in casa (EN fonte di verità, IT tipizzato contro EN) con provider React; backend language-agnostic sugli errori (codici stabili tradotti dal frontend). La lingua vive come colonna `language` sul modello `Settings` singleton. Spec: `docs/superpowers/specs/2026-07-11-i18n-it-en-design.md`.

**Tech Stack:** Next.js 16 (App Router, React 19, client components), FastAPI + SQLAlchemy + Pydantic, pytest.

## Global Constraints

- Branch di lavoro: `feat/i18n-it-en` (creato dalla Task 1 Step 0).
- Lingua base nel codice: **inglese**; l'italiano vive solo in `it.ts` (frontend) e nel catalogo `errors` dei dizionari. **Default runtime: `"en"`.**
- Valori lingua: letterali `"it" | "en"`; colonna `Settings.language` default `"en"`; chiave localStorage = `"sortory-lang"`.
- Test backend: **usare `backend/.venv/bin/python`** (Python 3.11). Il python di sistema è 3.9 e rompe su `X | None`. Comando: `cd backend && .venv/bin/python -m pytest tests -q`.
- Test frontend: `cd frontend && npm run build` e `npm run lint`.
- Next 16 gotcha: gli spazi JSX a fine riga spariscono → usare `{" "}` esplicito quando il testo va a capo.
- Nei task di migrazione UI **non cambiare markup/classi**: solo sostituzione di stringhe.
- Non toccare i file di altre feature: prima di ogni commit `git status` e stage esplicito dei soli file del task.
- Nomi propri / termini di dominio **invariati**: Sortory, Rekordbox, AcoustID, Discogs, MusicBrainz, PLAN, RETAG, RENAME, MOVE, DELETE, ISRC, MBID, BPM, `backend/.env`.
- `apiGet`/`apiSend` in `frontend/lib/api.ts` sono **privati** (non esportati): il modulo i18n consuma le funzioni pubbliche con nome (`getLanguage`/`setLanguage`, aggiunte nella Task 2), mai `apiGet` direttamente.

---

### Task 1: Backend — colonna lingua + endpoint `GET/PUT /api/settings/language`

**Files:**
- Modify: `backend/app/models.py` (colonna `language` su `Settings`)
- Modify: `backend/app/db.py` (`ensure_schema`: ALTER idempotente per `settings.language`)
- Modify: `backend/app/services/planning.py` (helper `get_language`, `set_language`)
- Modify: `backend/app/routers/settings.py` (route `GET/PUT /language`)
- Modify: `backend/app/schemas.py` (schema `LanguageSetting`)
- Create: `backend/tests/test_language_setting.py`

**Interfaces:**
- Consumes: `get_db` da `app/db.py`; `Settings` model, `get_settings` da `app/services/planning.py`.
- Produces:
  - `get_language(db: Session) -> str` — ritorna sempre `"it"` o `"en"`, default `"en"` (valori ignoti degradano).
  - `set_language(db: Session, value: str) -> Settings`.
  - `GET /api/settings/language -> {"language": "it"|"en"}`.
  - `PUT /api/settings/language` body `{"language": "it"|"en"}` (422 su altri valori).
  - Schema Pydantic `LanguageSetting(language: Literal["it","en"])`.

- [ ] **Step 0: Creare il branch**

```bash
cd /Users/lucadenegri/Develop/DjOrganizer01
git checkout -b feat/i18n-it-en
```

- [ ] **Step 1: Scrivere i test che falliscono**

```python
# backend/tests/test_language_setting.py
"""Impostazione lingua: colonna Settings.language + GET/PUT /api/settings/language.
Default EN; valori ignoti degradano a EN."""
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app

client = TestClient(app)


def _factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _override(factory):
    def _get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()
    return _get_db


def setup_function():
    app.dependency_overrides[get_db] = _override(_factory())


def teardown_function():
    app.dependency_overrides.clear()


def test_get_default_en():
    r = client.get("/api/settings/language")
    assert r.status_code == 200
    assert r.json() == {"language": "en"}


def test_put_then_get_it():
    assert client.put("/api/settings/language", json={"language": "it"}).status_code == 200
    assert client.get("/api/settings/language").json() == {"language": "it"}


def test_put_invalid_422():
    assert client.put("/api/settings/language", json={"language": "fr"}).status_code == 422


def test_get_language_helper():
    from app.services.planning import get_language, set_language
    factory = _factory()
    db = factory()
    try:
        assert get_language(db) == "en"          # default
        set_language(db, "it")
        assert get_language(db) == "it"
        set_language(db, "garbage")
        assert get_language(db) == "en"          # valore ignoto -> default
    finally:
        db.close()
```

- [ ] **Step 2: Verificare che falliscano**

Run: `cd backend && .venv/bin/python -m pytest tests/test_language_setting.py -v`
Expected: FAIL — `404` sugli endpoint (route assente) e `ImportError: cannot import name 'get_language'`.

- [ ] **Step 3: Colonna sul modello**

In `backend/app/models.py`, dentro `class Settings(Base)`, aggiungere dopo `folder_template`:

```python
    language: Mapped[str] = mapped_column(String, default="en")
```

- [ ] **Step 4: ALTER idempotente in `ensure_schema`**

In `backend/app/db.py`, dentro `ensure_schema`, dopo il blocco `scan_root` (stesso identico pattern), aggiungere:

```python
    if "settings" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("settings")}
        if "language" not in cols:
            with eng.begin() as conn:
                conn.execute(text("ALTER TABLE settings ADD COLUMN language VARCHAR DEFAULT 'en'"))
```

- [ ] **Step 5: Helper in `planning.py`**

In `backend/app/services/planning.py`, in coda al file:

```python
DEFAULT_LANGUAGE = "en"


def get_language(db: Session) -> str:
    """Lingua dell'app ("it" | "en"): valori sconosciuti degradano al default EN."""
    s = get_settings(db)
    return s.language if s.language in ("it", "en") else DEFAULT_LANGUAGE


def set_language(db: Session, value: str) -> Settings:
    s = get_settings(db)
    s.language = value
    s.updated_at = utcnow()
    db.commit()
    db.refresh(s)
    return s
```

(`get_settings`, `Settings`, `utcnow` sono già importati/definiti in questo file.)

- [ ] **Step 6: Schema Pydantic**

In `backend/app/schemas.py`, aggiungere (vicino agli altri schemi Settings):

```python
from typing import Literal  # se non già importato


class LanguageSetting(BaseModel):
    language: Literal["it", "en"]
```

- [ ] **Step 7: Route nel router settings**

In `backend/app/routers/settings.py`:
- aggiungere all'import degli schemi: `LanguageSetting`
- aggiungere all'import di planning: già presente `from app.services import planning`
- aggiungere le due route (il prefix `/api/settings` è già sul router):

```python
@router.get("/language", response_model=LanguageSetting)
def get_language_route(db: Session = Depends(get_db)):
    return LanguageSetting(language=planning.get_language(db))


@router.put("/language", response_model=LanguageSetting)
def put_language_route(body: LanguageSetting, db: Session = Depends(get_db)):
    planning.set_language(db, body.language)
    return body
```

Nota ordine route: definirle **prima** di `put_root_target` non è necessario
(path distinti: `/language` vs `/roots/{root_id}/target`), ma metterle subito
dopo `put_settings` per leggibilità.

- [ ] **Step 8: Verificare che passino**

Run: `cd backend && .venv/bin/python -m pytest tests/test_language_setting.py -v`
Expected: PASS (4 test).
Run: `cd backend && .venv/bin/python -m pytest tests -q`
Expected: PASS (suite intera, nessuna regressione).

- [ ] **Step 9: Commit**

```bash
git add backend/app/models.py backend/app/db.py backend/app/services/planning.py \
        backend/app/routers/settings.py backend/app/schemas.py backend/tests/test_language_setting.py
git commit -m "feat(i18n): colonna Settings.language + endpoint GET/PUT /api/settings/language (default EN)"
```

---

### Task 2: Frontend — modulo `lib/i18n` (dizionari + provider), wiring layout, API client

**Files:**
- Create: `frontend/lib/i18n/en.ts`
- Create: `frontend/lib/i18n/it.ts`
- Create: `frontend/lib/i18n/runtime.ts`
- Create: `frontend/lib/i18n/index.tsx`
- Modify: `frontend/lib/api.ts` (funzioni `getLanguage`/`setLanguage` + traduzione in `handle`)
- Modify: `frontend/app/layout.tsx`

**Interfaces:**
- Consumes: pattern `apiGet`/`apiSend` esistenti in `lib/api.ts` (privati; si aggiungono wrapper pubblici).
- Produces:
  - `useT(): Dictionary` — dizionario della lingua attiva.
  - `useI18n(): { lang: Language, setLang: (l: Language) => void, t: Dictionary }`.
  - `getCurrentLanguage(): Language`, `translateApiError(code, params, fallback): string` (da `runtime.ts`, ri-esportati da `index.tsx`).
  - Tipo `Dictionary = typeof en`, tipo `Language = "it" | "en"`.
  - `getLanguage(): Promise<{language: Language}>`, `setLanguage(l: Language): Promise<{language: Language}>` in `lib/api.ts`.
  - Tutti i task 3–10 consumano `useT`/`useI18n`; il task 11 consuma `translateApiError`.

- [ ] **Step 1: `en.ts` (fonte di verità, primi namespace)**

```ts
// frontend/lib/i18n/en.ts
// Fonte di verità delle chiavi i18n. NIENTE `as const`: i valori devono restare
// `string`/funzioni così `it.ts` può tipizzarsi con `typeof en`.
export const en = {
  common: {
    loading: "Loading…",
    save: "Save",
    cancel: "Cancel",
    close: "Close",
    confirm: "Confirm",
    delete: "Delete",
    search: "Search",
    all: "All",
    none: "None",
    error: "Error",
    retry: "Retry",
    never: "never",
    empty: "—",
  },
  nav: {
    tagline: "file → rekordbox",
    sources: "Sources",
    files: "Files",
    issues: "Issues",
    duplicates: "Duplicates",
    plan: "Plan",
    history: "History",
    settings: "Settings",
    toggleTheme: "Toggle theme",
    themePaper: "Paper",
    themeDark: "Dark",
  },
  settings: {
    languageLabel: "Language",
    languageIt: "Italiano",
    languageEn: "English",
  },
  errors: {} as Record<string, string | ((p: Record<string, unknown>) => string)>,
};

export type Dictionary = typeof en;
```

(I namespace `nav`/`common`/`settings` bastano ai Task 2–4; gli altri li
aggiungono i task di migrazione. `errors` si riempie nel Task 11.)

- [ ] **Step 2: `it.ts`**

```ts
// frontend/lib/i18n/it.ts
// Traduzione italiana: `Dictionary` (= typeof en) garantisce a compile-time che
// ogni chiave esista e nessuna sia di troppo.
import type { Dictionary } from "./en";

export const it: Dictionary = {
  common: {
    loading: "Caricamento…",
    save: "Salva",
    cancel: "Annulla",
    close: "Chiudi",
    confirm: "Conferma",
    delete: "Elimina",
    search: "Cerca",
    all: "Tutte",
    none: "Nessuna",
    error: "Errore",
    retry: "Riprova",
    never: "mai",
    empty: "—",
  },
  nav: {
    tagline: "file → rekordbox",
    sources: "Sources",
    files: "Files",
    issues: "Issues",
    duplicates: "Duplicates",
    plan: "Plan",
    history: "History",
    settings: "Settings",
    toggleTheme: "Cambia tema",
    themePaper: "Paper",
    themeDark: "Dark",
  },
  settings: {
    languageLabel: "Lingua",
    languageIt: "Italiano",
    languageEn: "English",
  },
  errors: {},
};
```

(I nomi di sezione nav — Sources/Files/… — restano identici nelle due lingue:
sono già in inglese nel design attuale e fanno da label di navigazione stabili.)

- [ ] **Step 3: `runtime.ts` (stato lingua fuori da React)**

Vive senza import da `lib/api.ts`, così `lib/api.ts` può importarlo (Task 11
Step 4) senza cicli di modulo:

```ts
// frontend/lib/i18n/runtime.ts
// Stato lingua accessibile fuori da React (es. lib/api.ts). Il provider in
// index.tsx lo tiene allineato al context. NIENTE import da lib/api.ts qui.
import { en, type Dictionary } from "./en";
import { it } from "./it";

export type Language = "it" | "en";

export const STORAGE_KEY = "sortory-lang";
export const DICTIONARIES: Record<Language, Dictionary> = { it, en };

let currentLanguage: Language = "en";

export function getCurrentLanguage(): Language {
  return currentLanguage;
}

export function setCurrentLanguage(next: Language): void {
  currentLanguage = next;
}

/** Traduce un codice errore API nella lingua attiva; `fallback` se il codice è ignoto. */
export function translateApiError(
  code: string,
  params: Record<string, unknown>,
  fallback: string,
): string {
  const entry = DICTIONARIES[currentLanguage].errors[code];
  if (typeof entry === "string") return entry;
  if (typeof entry === "function") return entry(params);
  return fallback;
}
```

- [ ] **Step 4: Provider `index.tsx`**

```tsx
// frontend/lib/i18n/index.tsx
"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { getLanguage, setLanguage } from "@/lib/api";
import { type Dictionary } from "./en";
import { en } from "./en";
import { DICTIONARIES, STORAGE_KEY, setCurrentLanguage, type Language } from "./runtime";

export type { Dictionary, Language };
export { getCurrentLanguage, translateApiError } from "./runtime";

const I18nContext = createContext<{
  lang: Language;
  t: Dictionary;
  setLang: (next: Language) => void;
}>({ lang: "en", t: en, setLang: () => {} });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Language>("en");

  useEffect(() => {
    /* localStorage evita il flash; il backend resta la fonte persistente. */
    const stored = localStorage.getItem(STORAGE_KEY);
    const initial: Language = stored === "it" ? "it" : "en";
    setCurrentLanguage(initial);
    setLangState(initial);
    document.documentElement.lang = initial;
    getLanguage()
      .then(({ language }) => {
        if (language !== initial) {
          setCurrentLanguage(language);
          setLangState(language);
          localStorage.setItem(STORAGE_KEY, language);
          document.documentElement.lang = language;
        }
      })
      .catch(() => undefined); // backend giù: si resta sulla lingua locale
  }, []);

  const setLang = (next: Language) => {
    setCurrentLanguage(next);
    setLangState(next);
    localStorage.setItem(STORAGE_KEY, next);
    document.documentElement.lang = next;
    setLanguage(next).catch(() => undefined);
  };

  return (
    <I18nContext.Provider value={{ lang, t: DICTIONARIES[lang], setLang }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useT(): Dictionary {
  return useContext(I18nContext).t;
}

export function useI18n() {
  return useContext(I18nContext);
}
```

- [ ] **Step 5: `lib/api.ts` — funzioni lingua + traduzione errori**

In `frontend/lib/api.ts`:

(a) In cima al file, dopo la riga `const API = …`, aggiungere l'import del runtime:

```ts
import { translateApiError, type Language } from "@/lib/i18n/runtime";
```

(b) Sostituire la funzione `handle` (righe ~96-109) con:

```ts
async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      const d = body.detail;
      if (d && typeof d === "object" && !Array.isArray(d) && typeof d.code === "string") {
        detail = translateApiError(d.code, d.params ?? {}, d.message ?? res.statusText);
      } else {
        detail = typeof d === "string" ? d : JSON.stringify(d);
      }
    } catch {
      /* keep statusText */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
```

(Finché il backend non manda `code` — prima del Task 11 — il ramo `else`
mantiene il comportamento attuale: nessuna rottura.)

(c) Nella sezione `// --- SETTINGS ---`, dopo `setRootTarget`, aggiungere:

```ts
export function getLanguage() {
  return apiGet<{ language: Language }>("/api/settings/language");
}
export function setLanguage(language: Language) {
  return apiSend<{ language: Language }>("PUT", "/api/settings/language", { language });
}
```

Nota cicli di modulo: `lib/api.ts` importa SOLO da `@/lib/i18n/runtime` (che
non importa da `lib/api.ts`) — mai da `@/lib/i18n` (index.tsx), che a sua volta
importa `getLanguage/setLanguage` e creerebbe un ciclo.

- [ ] **Step 6: Wiring nel layout**

In `frontend/app/layout.tsx`:
- `import { I18nProvider } from "@/lib/i18n";`
- avvolgere la shell: `<I18nProvider><EditorialShell>{children}</EditorialShell></I18nProvider>`
  (EditorialShell è server component: passarla come `children` a un provider
  client è corretto in App Router.)
- estendere `NO_FOUC` per impostare `lang="it"` solo se in localStorage c'è `"it"`
  (default HTML resta `lang="en"`):

```ts
const NO_FOUC = `(function(){try{var t=localStorage.getItem('djorganizer-theme');if(t==='paper'){document.documentElement.setAttribute('data-theme','paper');}var l=localStorage.getItem('sortory-lang');if(l==='it'){document.documentElement.lang='it';}}catch(e){}})();`;
```

- cambiare `<html lang="it" …>` in `<html lang="en" …>` (default EN server-side;
  il provider e lo script aggiornano al mount).

- [ ] **Step 7: Verifica build**

Run: `cd frontend && npm run build`
Expected: build OK, nessun errore TypeScript.

- [ ] **Step 8: Commit**

```bash
git add frontend/lib/i18n frontend/lib/api.ts frontend/app/layout.tsx
git commit -m "feat(i18n): dizionari en/it tipizzati, I18nProvider, wiring layout, client lingua"
```

---

### Task 3: Selettore lingua in Impostazioni

**Files:**
- Modify: `frontend/app/settings/page.tsx`

**Interfaces:**
- Consumes: `useI18n()` dal Task 2 (`lang`, `setLang`, `t`).
- Produces: UI per cambiare lingua (nessuna API nuova: `setLang` fa già PUT + localStorage).

- [ ] **Step 1: Aggiungere la sezione lingua**

In `frontend/app/settings/page.tsx`:
- import: `import { useI18n } from "@/lib/i18n";`
- dentro `SettingsPage()`, aggiungere `const { lang, setLang, t } = useI18n();`
- inserire una nuova `<section>` in cima al contenuto (subito dentro
  `<div className="flex max-w-2xl flex-col gap-6">`, prima del blocco `{offline && …}`),
  replicando lo stile delle sezioni esistenti. I bottoni copiano le classi del
  toggle già presente nel file (es. quelle del bottone "identifica ora":
  `border border-border px-1.5 py-0.5 text-[10px]`), adattando le dimensioni:

```tsx
<section className="flex flex-col gap-2">
  <h2 className="text-sm font-medium text-fg-strong">{t.settings.languageLabel}</h2>
  <div className="flex gap-2">
    <button
      type="button" onClick={() => setLang("it")} aria-pressed={lang === "it"}
      className={`border px-2 py-1 text-xs uppercase tracking-wider ${lang === "it" ? "border-border-strong bg-surface-2 text-fg-strong" : "border-border text-muted hover:text-fg"}`}
    >{t.settings.languageIt}</button>
    <button
      type="button" onClick={() => setLang("en")} aria-pressed={lang === "en"}
      className={`border px-2 py-1 text-xs uppercase tracking-wider ${lang === "en" ? "border-border-strong bg-surface-2 text-fg-strong" : "border-border text-muted hover:text-fg"}`}
    >{t.settings.languageEn}</button>
  </div>
</section>
```

(La sezione lingua deve stare **fuori** dal blocco `{settings && (…)}` così è
visibile anche se il backend è offline — il toggle lavora comunque su
localStorage.)

- [ ] **Step 2: Build + lint**

Run: `cd frontend && npm run build && npm run lint`
Expected: PASS.

- [ ] **Step 3: Verifica manuale**

Avviare backend (`cd backend && .venv/bin/python -m uvicorn app.main:app --reload --port 8010`)
e frontend (`cd frontend && npm run dev`). Su `/settings` cambiare lingua e
verificare: 1) i bottoni riflettono la scelta (`aria-pressed`),
2) `localStorage["sortory-lang"]` aggiornato, 3) dopo reload
`GET /api/settings/language` risponde col nuovo valore.

- [ ] **Step 4: Commit**

```bash
git add frontend/app/settings/page.tsx
git commit -m "feat(i18n): selettore lingua IT/EN in Impostazioni"
```

---

### Procedura comune ai task 4–10 (migrazione stringhe UI)

Ogni task di migrazione segue ESATTAMENTE questi passi (ripetuti per riferimento;
l'esecutore di un singolo task legge questo blocco + il suo task):

1. Per ogni file del blocco: individuare TUTTE le stringhe italiane user-visible
   — testo JSX, attributi `aria-label`/`title`/`placeholder`/`alt`, stringhe in
   costanti/oggetti (label di select, badge di stato, messaggi). Aiuto:
   `grep -nE '[àèéìòù]|Nessun|Carica|Salva|Annulla|Errore|vuoto|corso|trovat|corri' <file>`
   — ma la fonte di verità è la LETTURA del file, il grep non cattura tutto
   (molte stringhe italiane non hanno accenti).
2. Aggiungere le chiavi al namespace del blocco in `en.ts` **E** `it.ts` nello
   stesso commit (il type-check fallisce se una manca). Naming: camelCase
   descrittivo (`emptyState`, `saveTemplates`, `pathAbsolute`). Stringhe con
   parametri = funzioni: `filesCount: (n: number) => n === 1 ? "1 file" : n + " files"`.
3. Nei componenti: `const t = useT();`. Il componente deve essere client
   (`"use client"`): quasi tutti lo sono già; se un file è server component senza
   interattività, aggiungere `"use client"` è accettabile (l'app è dietro
   provider client comunque).
4. Sostituire le stringhe con `t.<ns>.<chiave>`. **NON cambiare markup né classi.**
   Spazi JSX di Next 16: se il testo andava a capo, usare `{" "}` esplicito.
5. `cd frontend && npm run build && npm run lint` → devono passare.
6. Verifica visiva rapida col dev server in ENTRAMBE le lingue sulle pagine toccate.
7. Commit dei soli file del blocco + `en.ts`/`it.ts`.

Regole di contenuto:
- Nomi propri e termini di dominio invariati (vedi Global Constraints).
- Testo EN: conciso, sentence case; i micro-label uppercase del design (es.
  `uppercase tracking-wider`) restano gestiti dalle classi CSS, la stringa va in
  minuscolo naturale.
- I commenti italiani nel codice NON si toccano (non sono UI).

---

### Task 4: Migrazione shell, navigazione e barra job

**Files:**
- Modify: `frontend/components/index-nav.tsx`, `frontend/components/theme-toggle.tsx`, `frontend/components/clock.tsx`, `frontend/components/jobs-provider.tsx`, `frontend/components/page-layout.tsx`, `frontend/components/ui.tsx`
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts` (namespace `nav` già presente; ampliare `common`; nuovo namespace `jobs` se la barra job ha etichette)

**Interfaces:**
- Consumes: `useT()` dal Task 2. Le chiavi `nav.*` esistono già dal Task 2.
- Produces: shell bilingue; namespace `jobs` per la barra job (se presente).

- [ ] **Step 1: Seguire la "Procedura comune" su ogni file del blocco.**

Dettaglio noto:
- `index-nav.tsx`: la tagline `"file → rekordbox"` → `{t.nav.tagline}`. Le label
  `NAV` (Sources/Files/…) restano invariate (già inglesi, label stabili) — non
  serve toccarle. Il logo `SORTORY` resta.
- `theme-toggle.tsx`: `aria-label="Cambia tema"` → `aria-label={t.nav.toggleTheme}`;
  `{theme === "dark" ? "Paper" : "Dark"}` → `{theme === "dark" ? t.nav.themePaper : t.nav.themeDark}`.
  Aggiungere `const t = useT();` (il componente è già `"use client"`).
- `clock.tsx`, `jobs-provider.tsx`, `page-layout.tsx`, `ui.tsx`: leggere e
  tradurre ogni stringa italiana user-visible trovata. Le etichette dei job (se
  `jobs-provider` ne definisce) vanno nel namespace `jobs`. NB: eventuali
  `phase`/`error` che arrivano dal backend NON si toccano qui (restano
  language-agnostic; gli errori diventano codici nel Task 11).

- [ ] **Step 2: Build + lint** — `cd frontend && npm run build && npm run lint` → PASS.
- [ ] **Step 3: Verifica visiva IT/EN (toggle su /settings, girare le pagine).**
- [ ] **Step 4: Commit**

```bash
git add frontend/components/index-nav.tsx frontend/components/theme-toggle.tsx \
        frontend/components/clock.tsx frontend/components/jobs-provider.tsx \
        frontend/components/page-layout.tsx frontend/components/ui.tsx frontend/lib/i18n
git commit -m "feat(i18n): traduzione shell, navigazione e barra job"
```

---

### Task 5: Migrazione Sources

**Files:**
- Modify: `frontend/app/sources/page.tsx`, `frontend/components/sources-table.tsx`, `frontend/components/add-source.tsx`
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts` (namespace `sources`)

**Interfaces:**
- Consumes: `useT()`; Procedura comune (sopra).
- Produces: namespace `sources` completo (lista radici, form aggiunta, stati, conteggi present/missing).

- [ ] **Step 1: Applicare la Procedura comune a ogni file del blocco.** Attenzione ai conteggi (present/missing) come funzioni `(n: number) => string` e alle stringhe di stato/placeholder del form.
- [ ] **Step 2: Build + lint** → PASS.
- [ ] **Step 3: Verifica visiva IT/EN di /sources.**
- [ ] **Step 4: Commit** — `git add frontend/app/sources frontend/components/sources-table.tsx frontend/components/add-source.tsx frontend/lib/i18n && git commit -m "feat(i18n): traduzione Sources"`

---

### Task 6: Migrazione Files

**Files:**
- Modify: `frontend/app/files/page.tsx`, `frontend/components/files-table.tsx`
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts` (namespace `files`)

**Interfaces:**
- Consumes: `useT()`; Procedura comune (sopra).
- Produces: namespace `files` completo (filtri/facets, ordinamento, colonne tabella, empty state, helper `fmtDuration`/`fmtDate` — vedi nota).

- [ ] **Step 1: Applicare la Procedura comune.** Ogni option label di select (sort/status/facets) è una chiave. **Helper in `lib/api.ts`:** `fmtDate` ritorna `"mai"` e usa `toLocaleString("it-IT", …)`; `fmtDuration` ritorna `"—"`. Questi sono usati da più pagine: NON localizzarli via `useT` (sono funzioni pure fuori da React). Regola: lasciare `fmtDuration`/`fmtDate` come sono in questo task (il `"—"` è neutro; `"mai"`/locale data sono un dettaglio minore accettabile) e annotare nel commit che la localizzazione date è fuori scope. Le stringhe user-visible NEI componenti (empty state, header) si traducono normalmente.
- [ ] **Step 2: Build + lint** → PASS.
- [ ] **Step 3: Verifica visiva IT/EN di /files.**
- [ ] **Step 4: Commit** — `git commit -m "feat(i18n): traduzione Files"` (stage: file del blocco + dizionari).

---

### Task 7: Migrazione Issues

**Files:**
- Modify: `frontend/app/issues/page.tsx`, `frontend/components/issues-table.tsx`
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts` (namespace `issues`)

**Interfaces:**
- Consumes: `useT()`; Procedura comune (sopra).
- Produces: namespace `issues` completo (filtri severità/tipo/stato, azioni bulk, bottoni AI "Risolvi con AI"/"Suggerisci generi", provider-suggest, anteprima cover, input fix manuale, stati open/accepted/dismissed).

- [ ] **Step 1: Applicare la Procedura comune.** Molte stringhe: bottoni AI, messaggi di risultato (`X identificati, Y suggeriti…` come funzioni con params), label di severità/stato. Il campo `issue.detail` e `issue.type` arrivano dal backend: sono dati, NON si traducono qui (restano com'è dal DB).
- [ ] **Step 2: Build + lint** → PASS.
- [ ] **Step 3: Verifica visiva IT/EN di /issues.**
- [ ] **Step 4: Commit** — `git commit -m "feat(i18n): traduzione Issues"`.

---

### Task 8: Migrazione Plan e Apply

**Files:**
- Modify: `frontend/app/plan/page.tsx`, `frontend/components/plan-ops.tsx`, `frontend/components/apply-modal.tsx`
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts` (namespace `plan`)

**Interfaces:**
- Consumes: `useT()`; Procedura comune (sopra).
- Produces: namespace `plan` completo (statistiche piano, tipi op RETAG/RENAME/MOVE/DELETE come label tradotte ma i codici kind restano, conflitti/skipped, modale apply con conferma, stati job apply).

- [ ] **Step 1: Applicare la Procedura comune.** I `kind` (RETAG/…) sono codici dal backend: la loro **label descrittiva** si traduce (namespace `plan.opKind`), il codice grezzo no. Le statistiche (`n_move` ecc.) diventano stringhe con conteggi. `Conflict.detail` arriva dal backend → non tradurre qui.
- [ ] **Step 2: Build + lint** → PASS.
- [ ] **Step 3: Verifica visiva IT/EN di /plan e della modale apply.**
- [ ] **Step 4: Commit** — `git commit -m "feat(i18n): traduzione Plan e Apply"`.

---

### Task 9: Migrazione Duplicates e History

**Files:**
- Modify: `frontend/app/duplicates/page.tsx`, `frontend/components/dup-group.tsx`, `frontend/app/history/page.tsx`
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts` (namespace `duplicates`, `history`)

**Interfaces:**
- Consumes: `useT()`; Procedura comune (sopra).
- Produces: namespace `duplicates` e `history` completi (gruppi duplicati keep/remove, keeper override, dismiss, lista run applied/undone, undo).

- [ ] **Step 1: Applicare la Procedura comune.** Stati `keep`/`remove`, `applied`/`undone` sono codici dal backend: si traduce la label mostrata (namespace dedicato), non il dato.
- [ ] **Step 2: Build + lint** → PASS.
- [ ] **Step 3: Verifica visiva IT/EN di /duplicates e /history.**
- [ ] **Step 4: Commit** — `git commit -m "feat(i18n): traduzione Duplicates e History"`.

---

### Task 10: Migrazione Impostazioni (resto) + sweep finale UI

**Files:**
- Modify: `frontend/app/settings/page.tsx` (tutte le stringhe italiane rimaste oltre al selettore del Task 3)
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts` (ampliare `settings`)

**Interfaces:**
- Consumes: `useT()`; Procedura comune (sopra).
- Produces: UI frontend 100% bilingue.

- [ ] **Step 1: Applicare la Procedura comune a `settings/page.tsx`.** Tradurre: guida (`<PageLayout guide>`), sezione "Organizzazione" e testi lunghi, label template nome/cartelle, anteprima percorso, blocco destinazione per radice (`RootRow`), badge stato provider (`StatusBadge`: configurato/collegato/mancante), sezione Provider, bottoni ("salva template", "salva", "identifica ora"/"identificazione…"), messaggi (`fpResult`, "Backend non raggiungibile…", catch "Errore" → `t.common.error`). Il `title="Settings"` di `PageLayout` resta o diventa `t.nav.settings`.
- [ ] **Step 2: Sweep finale UI** — girare tutte le pagine con:
  `grep -rnE '[àèéìòù]' frontend/app frontend/components | grep -E '\.tsx:' | grep -v '^\s*//'`
  → nessuna stringa UI residua (solo eventuali commenti). Le stringhe italiane
  senza accento sfuggite si trovano rileggendo le pagine principali nel dev
  server in EN (una parola italiana salta all'occhio). Sistemare i residui qui.
- [ ] **Step 3: Build + lint** → PASS.
- [ ] **Step 4: Verifica visiva IT/EN di /settings e sweep delle altre pagine.**
- [ ] **Step 5: Commit** — `git commit -m "feat(i18n): traduzione Impostazioni e sweep finale UI"`.

---

### Task 11: Backend — codici errore stabili (`api_error`) + traduzione in `lib/api.ts`

**Files:**
- Create: `backend/app/core/http_errors.py`
- Create: `backend/tests/test_http_errors.py`
- Modify: tutti i router con `HTTPException(detail="<italiano>")`: `plan.py`, `issues.py`, `duplicates.py`, `sources.py`, `settings.py`, `scan.py`, `history.py`, `apply.py`
- Modify: `frontend/lib/i18n/en.ts`, `frontend/lib/i18n/it.ts` (namespace `errors`)
- Modify: test backend che asseriscono su stringhe di errore di questi router

**Interfaces:**
- Consumes: `translateApiError` dal Task 2 (già cablato in `lib/api.ts` handle).
- Produces: `api_error(status_code: int, code: str, message: str, **params) -> HTTPException` con `detail = {"code", "message", "params"?}`; convenzione codici `snake_case` `<entità>_<problema>`. I test asseriscono su `r.json()["detail"]["code"]`.

- [ ] **Step 1: Test del helper**

```python
# backend/tests/test_http_errors.py
"""api_error: HTTPException con detail strutturato {code, message, params?}."""
from app.core.http_errors import api_error


def test_detail_strutturato():
    exc = api_error(404, "plan_draft_missing", "No draft plan")
    assert exc.status_code == 404
    assert exc.detail == {"code": "plan_draft_missing", "message": "No draft plan"}


def test_params_opzionali():
    exc = api_error(409, "job_running", "Job already running", job="scan")
    assert exc.detail["params"] == {"job": "scan"}
```

Run: `cd backend && .venv/bin/python -m pytest tests/test_http_errors.py -v` → FAIL (modulo mancante).

- [ ] **Step 2: Implementare il helper**

```python
# backend/app/core/http_errors.py
"""Errori HTTP con codice stabile: il frontend traduce `code` nella lingua
attiva; `message` (inglese) è il fallback leggibile per debug/curl."""
from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str, **params) -> HTTPException:
    detail: dict = {"code": code, "message": message}
    if params:
        detail["params"] = params
    return HTTPException(status_code=status_code, detail=detail)
```

Run: `cd backend && .venv/bin/python -m pytest tests/test_http_errors.py -v` → PASS.

- [ ] **Step 3: Migrare i router**

Sostituire ogni `raise HTTPException(status_code=S, detail="<italiano>")` con
`raise api_error(S, "<code>", "<English message>")`. In cima a ogni router
toccato: `from app.core.http_errors import api_error` (e rimuovere l'import di
`HTTPException` se non più usato — verificare: alcuni router lo usano solo qui).

**ATTENZIONE — NON toccare** questi due `detail=`, che NON sono HTTPException:
- `issues.py:30` — `IssueRead(... detail=issue.detail ...)` (campo di schema)
- `issues.py:236` — `Issue(... detail="copertina mancante" ...)` (creazione model DB, è un dato persistito, non un errore HTTP)

Mappatura completa (verificare a mano che copra tutte le `raise HTTPException`):

| File:riga | status | code | message (EN) |
|---|---|---|---|
| plan.py:22 | 404 | `plan_draft_missing` | No draft plan |
| issues.py:60 | 400 | `issue_status_invalid` | Invalid status |
| issues.py:63 | 404 | `issue_not_found` | Issue not found |
| issues.py:65 | 400 | `issue_not_autofixable` | Issue is not auto-fixable |
| issues.py:75 | 400 | `issue_status_invalid` | Invalid status |
| issues.py:100 | 404 | `issue_not_found` | Issue not found |
| issues.py:102 | 400 | `issue_field_not_editable` | Field can't be edited by hand |
| issues.py:105 | 400 | `issue_value_empty` | Empty value |
| issues.py:343 | 404 | `thumb_missing` | No thumbnail |
| issues.py:350 | 409 | `scan_or_apply_running` | Scan or apply in progress |
| duplicates.py:38 | 404 | `dup_group_not_found` | Group not found |
| duplicates.py:41 | 400 | `dup_file_not_member` | file_id is not a member of the group |
| duplicates.py:55 | 404 | `dup_group_not_found` | Group not found |
| sources.py:41 | 400 | `source_path_invalid` | Path does not exist or is not a folder |
| sources.py:43 | 409 | `source_already_present` | Root already present |
| sources.py:55 | 404 | `source_not_found` | Root not found |
| settings.py:40 | 400 | `target_root_not_absolute` | target_root must be an absolute path |
| settings.py:42 | 404 | `source_not_found` | Root not found |
| scan.py:18 | 409 | `apply_running` | Apply in progress |
| history.py:30 | 404 | `run_not_found` | Run not found |
| history.py:32 | 400 | `run_not_applied` | Run is not in 'applied' state |
| apply.py:17 | 409 | `scan_running` | Scan in progress |
| apply.py:19 | 400 | `plan_draft_missing` | No draft plan to apply |

(Codici riusati intenzionalmente dove il significato è identico: `issue_not_found`,
`issue_status_invalid`, `dup_group_not_found`, `source_not_found`,
`plan_draft_missing`.)

- [ ] **Step 4: Riempire `errors` nei dizionari**

In `frontend/lib/i18n/en.ts`, sostituire `errors: {} as …` con l'oggetto pieno
(valore EN = colonna message della tabella; chiavi uniche, i codici riusati una
sola volta):

```ts
errors: {
  plan_draft_missing: "No draft plan.",
  issue_status_invalid: "Invalid status.",
  issue_not_found: "Issue not found.",
  issue_not_autofixable: "Issue is not auto-fixable.",
  issue_field_not_editable: "This field can't be edited by hand.",
  issue_value_empty: "Empty value.",
  thumb_missing: "No thumbnail.",
  scan_or_apply_running: "A scan or apply is already running.",
  dup_group_not_found: "Group not found.",
  dup_file_not_member: "This file is not a member of the group.",
  source_path_invalid: "The path does not exist or is not a folder.",
  source_already_present: "Root already present.",
  source_not_found: "Root not found.",
  target_root_not_absolute: "The destination must be an absolute path.",
  apply_running: "An apply is already running.",
  scan_running: "A scan is already running.",
  run_not_found: "Run not found.",
  run_not_applied: "This run is not in the 'applied' state.",
} as Record<string, string | ((p: Record<string, unknown>) => string)>,
```

In `frontend/lib/i18n/it.ts`, `errors:` con le stringhe italiane originali dei
`raise` (riprese dal codice attuale), stesse chiavi:

```ts
errors: {
  plan_draft_missing: "Nessun piano draft.",
  issue_status_invalid: "Status non valido.",
  issue_not_found: "Issue non trovato.",
  issue_not_autofixable: "Issue non auto-fixabile.",
  issue_field_not_editable: "Campo non correggibile a mano.",
  issue_value_empty: "Valore vuoto.",
  thumb_missing: "Nessuna thumbnail.",
  scan_or_apply_running: "Scan o apply in corso.",
  dup_group_not_found: "Gruppo non trovato.",
  dup_file_not_member: "Il file non è membro del gruppo.",
  source_path_invalid: "Il path non esiste o non è una cartella.",
  source_already_present: "Radice già presente.",
  source_not_found: "Radice non trovata.",
  target_root_not_absolute: "La destinazione deve essere un path assoluto.",
  apply_running: "Apply in corso.",
  scan_running: "Scan in corso.",
  run_not_found: "Run non trovata.",
  run_not_applied: "La run non è in stato 'applied'.",
},
```

- [ ] **Step 5: Aggiornare i test backend coinvolti**

Trovare i test che asseriscono sulle stringhe italiane di errore:
`grep -rn "detail" backend/tests | grep -iE "non trovat|non valido|in corso|vuoto|già presente|draft|assoluto"`.
Per ciascuno, cambiare l'assert da stringa a codice, es.:
`assert r.json()["detail"] == "Radice non trovata"` →
`assert r.json()["detail"]["code"] == "source_not_found"`.

- [ ] **Step 6: Test + build**

Run: `cd backend && .venv/bin/python -m pytest tests -q` → PASS (tutta la suite).
Run: `cd frontend && npm run build && npm run lint` → PASS.

- [ ] **Step 7: Verifica finale codici**

Run: `grep -rnE 'HTTPException\(.*detail="[^"]*[àèéìòù]' backend/app/routers` → zero risultati.
(Nota: `issues.py:236` usa `detail=` su un model, senza `HTTPException`, quindi
non compare.)

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/http_errors.py backend/tests/test_http_errors.py \
        backend/app/routers backend/tests frontend/lib/i18n
git commit -m "feat(i18n): codici errore stabili (api_error) su tutti i router, traduzione in lib/api.ts"
```

---

### Task 12: Verifica finale, documentazione e chiusura branch

**Files:**
- Modify: `README.md` (nota breve i18n, se il README elenca le feature)
- Modify: eventuale `docs/` di progetto che descrive l'architettura (se esiste una sezione features)

**Interfaces:**
- Consumes: tutto quanto sopra.
- Produces: branch pronto per merge.

- [ ] **Step 1: Suite backend completa** — `cd backend && .venv/bin/python -m pytest tests -q` → PASS, zero failure.
- [ ] **Step 2: Frontend** — `cd frontend && npm run build && npm run lint` → PASS.
- [ ] **Step 3: Sweep residui** —
  `grep -rnE '[àèéìòù]' frontend/app frontend/components | grep -E '\.tsx:' | grep -v '^\s*//'` (nessuna stringa UI residua; commenti ok) e
  `grep -rnE 'HTTPException\(.*detail="[^"]*[àèéìòù]' backend/app` (zero).
- [ ] **Step 4: Verifica manuale end-to-end** — dev server (backend porta 8010 + frontend): toggle lingua su /settings; girare Sources, Files, Issues (provare un bottone AI se configurato), Plan (build), Duplicates, History in ENTRAMBE le lingue; provocare un errore (es. aggiungere una radice con path inesistente) e verificare il messaggio tradotto sia in IT che in EN.
- [ ] **Step 5: Docs** — aggiornare `README.md` con una riga sulla feature bilingue (default EN, toggle in Impostazioni) se il README elenca le funzionalità; altrimenti saltare.
- [ ] **Step 6: Commit docs** (se toccati) — `git add README.md docs && git commit -m "docs(i18n): nota feature bilingue IT/EN"`.
- [ ] **Step 7: Chiusura branch** — usare la skill superpowers:finishing-a-development-branch (default utente: merge su `main` + push).
