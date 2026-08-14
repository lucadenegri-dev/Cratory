# Design — Internazionalizzazione IT/EN (i18n)

Data: 2026-07-11
Stato: approvato (brainstorming con Luca)
Riferimento: adattato dalla spec gemella di Cratory
(`DJProject01/.claude/worktrees/i18n-it-en/docs/superpowers/specs/2026-07-11-i18n-it-en-design.md`).

## Obiettivo

Sortory (cartella locale `DjOrganizer01`) diventa bilingue italiano/inglese.
Perimetro: UI frontend + messaggi di errore backend. La lingua si seleziona con
un toggle in Impostazioni (nessun routing per locale: app personale mono-utente,
niente SEO). Nel codice la lingua base è l'inglese; l'italiano è il file di
traduzione. **Default alla prima esecuzione: inglese** (coincide con la lingua
base del codice).

## Differenze rispetto a Cratory (perché questa spec è più corta)

Sortory condivide con Cratory lo stesso stack (Next 16 / React 19 / Tailwind 4)
e la stessa shell editoriale, quindi la ricetta si trasferisce quasi 1:1. Tre
differenze riducono il lavoro:

1. **Persistenza**: Cratory ha un key-value store generico (`AppState`); Sortory
   no — ha un modello `Settings` a riga singola (`id=1`, con `naming_template`/
   `folder_template`). La lingua vive come **colonna `language` su `Settings`**,
   non un nuovo store.
2. **AI fuori scope**: l'AI di Sortory (`ai_tags.py`: risolvi artist/title,
   suggerisci generi) estrae **solo dati** strutturati, nessuna prosa
   user-visible. Non c'è output AI da localizzare → la "Fase AI" della spec di
   Cratory qui non esiste. I prompt restano in italiano (sono istruzioni al
   modello, non UI).
3. **Scala minore**: ~23 file `.tsx` (vs ~51) e **25** `HTTPException` con
   `detail` italiano (vs ~82).

## Decisioni chiave

- **Nessuna libreria i18n**: dizionario TypeScript fatto in casa, type-safe. Per
  un'app mono-utente la type-safety a compile-time vale più dell'ecosistema di
  next-intl; plurali e interpolazione si gestiscono con funzioni TS.
- **Backend language-agnostic sugli errori**: gli errori diventano codici
  stabili; la traduzione avviene solo nel frontend. Niente doppio catalogo lato
  server.
- **Default EN**: `Settings.language` default `"en"`; ogni fallback (valore
  ignoto, backend giù, localStorage vuoto) degrada a `"en"`.

## 1. Impostazione lingua (backend)

- Nuova colonna `language` (`String`, default `"en"`) sul modello `Settings`
  singleton in `backend/app/models.py`.
- Helper `get_language(db: Session) -> str` (in `app/services/planning.py`,
  accanto a `get_settings`): legge `Settings.language`, valori diversi da
  `"it"`/`"en"` degradano a `"en"`.
- Il router esistente `app/routers/settings.py` (prefix `/api/settings`) aggiunge
  `GET /api/settings/language -> {"language": "it"|"en"}` e
  `PUT /api/settings/language` body `{"language": "it"|"en"}` (422 su altri
  valori, via `Literal["it","en"]` Pydantic). Riuso di `get_settings`/
  `update_settings` di `planning`.
- Il frontend mirrora il valore in `localStorage` (chiave `sortory-lang`) per
  evitare il flash di lingua sbagliata al primo render (stesso pattern del
  theme-toggle, che usa `djorganizer-theme`).

Nota migrazione DB: il DB SQLite (`djorganizer.db`) esistente non ha la colonna
`language`. La riga `Settings` viene creata/letta da `get_settings`; l'aggiunta
della colonna con `default="en"` va gestita come le altre colonne del modello
(SQLite: `ALTER TABLE settings ADD COLUMN language ... DEFAULT 'en'` se il DB è
già creato, oppure ricreazione in dev). Verificare in fase di implementazione
come Sortory gestisce le migrazioni (nessun Alembic osservato → `create_all` +
eventuale ALTER idempotente all'avvio, coerente col resto del progetto).

## 2. Frontend — modulo `frontend/lib/i18n/`

- `en.ts`: dizionario tipizzato, **fonte di verità delle chiavi**, organizzato
  per pagina/componente (`files.title`, `settings.languageLabel`, …). NIENTE
  `as const` (i valori devono restare `string`/funzioni così `it.ts` si tipizza
  con `typeof en`). Stringhe con parametri = funzioni tipizzate, es.
  `filesCount: (n: number) => n === 1 ? "1 file" : n + " files"`. Plurali e
  interpolazione sono TypeScript puro, nessun mini-DSL. `export type Dictionary
  = typeof en;`.
- `it.ts`: `const it: Dictionary = …` — chiave mancante o extra = errore di
  compilazione.
- `runtime.ts`: stato lingua **fuori da React** (`getCurrentLanguage`,
  `setCurrentLanguage`, `translateApiError(code, params, fallback)`), senza
  import da `lib/api.ts` così `lib/api.ts` può importarlo senza cicli di modulo.
  Chiave localStorage `STORAGE_KEY = "sortory-lang"`.
- `index.tsx`: `I18nProvider` + hook `useT(): Dictionary` e `useI18n(): { lang,
  setLang, t }`, sul pattern del provider tema. Al mount: legge localStorage →
  imposta lingua ottimistica → poi `GET /api/settings/language` per allineare al
  backend (se giù, resta sulla lingua locale). `setLang` fa `PUT` + localStorage
  + aggiorna `document.documentElement.lang`.
- Fallback runtime: chiave assente (impossibile a compile-time) → si mostra
  l'inglese.
- Wiring in `frontend/app/layout.tsx`: avvolgere la shell con `<I18nProvider>`;
  estendere lo script `NO_FOUC` per impostare `document.documentElement.lang =
  'it'` solo se `localStorage['sortory-lang'] === 'it'` (default HTML `lang="en"`).

Migrazione pagina per pagina (~23 file `.tsx`): sostituzione delle stringhe
hardcoded con `t.xxx`, **senza cambiare markup/classi**. Gotcha Next 16 sugli
spazi JSX a fine riga: usare `{" "}` esplicito quando il testo va a capo (vedi
`frontend/CLAUDE.md` se presente).

Blocchi di migrazione (aree di Sortory):
1. shell + navigazione (`editorial-shell`, `index-nav`, `theme-toggle`,
   `page-layout`, `ui`, `jobs-provider`, `clock`).
2. Sources (`app/sources`, `sources-table`, `add-source`).
3. Files (`app/files`, `files-table`).
4. Issues (`app/issues`, `issues-table`).
5. Plan / Apply (`app/plan`, `plan-ops`, `apply-modal`).
6. Duplicates / History (`app/duplicates`, `dup-group`, `app/history`).
7. Settings (`app/settings`) — include il selettore lingua.

## 3. Backend — codici errore (trattamento completo)

- Helper `api_error(status_code, code, message, **params) -> HTTPException` (in
  `backend/app/core/http_errors.py`, o modulo equivalente se `app/core` non
  esiste): `detail = {"code", "message", "params"?}`. Il `message` inglese resta
  come fallback leggibile per debug/curl. Convenzione codici `snake_case`
  `<entità>_<problema>` (es. `root_not_found`, `target_root_not_absolute`).
- I ~25 `HTTPException(detail="<italiano>")` nei router (`issues.py` 11,
  `duplicates.py` 3, `sources.py` 3, `history.py` 2, `apply.py` 2,
  `settings.py` 2, `plan.py` 1, `scan.py` 1) passano a `api_error(...)`.
- `frontend/lib/api.ts`: se `detail` è un oggetto con `code`, traduce dal
  namespace `errors.*` via `translateApiError`; altrimenti mostra `message` o la
  stringa com'è → migrazione endpoint-per-endpoint senza rotture.
- Namespace `errors` nei dizionari: chiave = codice, valore = stringa EN (IT in
  `it.ts` = stringa italiana originale del `raise`); params → funzione.
- Test backend: gli assert su stringhe italiane di errore passano ad asserire su
  `r.json()["detail"]["code"]` (più stabile delle stringhe).

## 4. AI — fuori scope

`ai_tags.py` (`suggest`, `suggest_genres`) restituisce dati strutturati
(`artist`/`title`, `genre`), non prosa. Nessun output user-visible dipendente
dalla lingua → nessuna modifica. I prompt restano in italiano (istruzioni al
modello). Questo è deliberato.

## 5. Testing

- Backend: nuovi test per `GET/PUT /api/settings/language` e per `api_error`;
  test errori esistenti aggiornati ad asserire sul `code`. Comando:
  `backend/.venv/bin/python -m pytest tests -q` (venv Python 3.11 — il python di
  sistema è 3.9 e rompe su `X | None`).
- Frontend: la rete di sicurezza principale è il type-check (chiavi complete per
  costruzione); `npm run build` + `npm run lint` come gate. Verifica manuale col
  dev server sulle pagine principali in entrambe le lingue.

## 6. Fasi di lavoro (ognuna committabile e funzionante da sola)

1. **Infrastruttura**: colonna `language` + helper + endpoint (backend) +
   `I18nProvider`/`useT()` + selettore in Impostazioni.
2. **Frontend UI**: migrazione pagine a `t.*` nei 7 blocchi sopra.
3. **Backend**: `api_error` + aggiornamento `lib/api.ts` + catalogo `errors` +
   test.

L'app resta in italiano (stringhe hardcoded) finché il toggle e la migrazione
non procedono, poi migra progressivamente; il default runtime EN diventa
visibile man mano che le pagine adottano `t.*`.

## Fuori scope

- Routing per locale (`/en`, `/it`), SEO, negotiation `Accept-Language`.
- Traduzione della documentazione di progetto (`docs/` resta com'è).
- Lingue oltre IT/EN (la struttura le permette, ma non si predispone nulla).
- Localizzazione output AI (l'AI produce solo dati).
