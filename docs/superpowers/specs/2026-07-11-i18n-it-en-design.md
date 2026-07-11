# Design — Internazionalizzazione IT/EN (i18n)

Data: 2026-07-11
Stato: approvato (brainstorming con Luca)

## Obiettivo

Cratory diventa bilingue italiano/inglese. Perimetro completo: UI frontend,
messaggi di errore backend e output AI (narrativa/spiegazioni). La lingua si
seleziona con un toggle in Impostazioni (nessun routing per locale: app
personale mono-utente, niente SEO). Nel codice la lingua base è l'inglese;
l'italiano è il file di traduzione. Default alla prima esecuzione: italiano.

## Decisioni chiave

- **Nessuna libreria i18n**: dizionario TypeScript fatto in casa, type-safe.
  Per un'app mono-utente la type-safety a compile-time vale più dell'ecosistema
  di next-intl; plurali e interpolazione si gestiscono con funzioni TS.
- **Backend language-agnostic**: gli errori diventano codici stabili; la
  traduzione avviene solo nel frontend. Niente doppio catalogo lato server.
- **AI parametrica**: la lingua selezionata viene iniettata nei prompt; la
  validazione Pydantic non cambia (valida struttura, non lingua).

## 1. Impostazione lingua

- Nuova chiave `language` (`"it"` | `"en"`, default `"it"`) nel key-value store
  esistente `AppState` (stesso pattern di `soundcloud_username`).
- Nuovo router `app/routers/settings.py` con `GET/PUT /api/settings/language`,
  implementato con gli helper esistenti `get_state`/`set_state` (stesso pattern
  di `PUT /api/soundcloud/config`).
- La pagina Impostazioni aggiunge un selettore IT/EN accanto al tema.
- Il frontend mirrora il valore in `localStorage` per evitare flash di lingua
  sbagliata al primo render (stesso pattern del theme-toggle).

## 2. Frontend — modulo `frontend/lib/i18n/`

- `en.ts`: dizionario tipizzato, fonte di verità delle chiavi, organizzato per
  pagina/componente (`library.title`, `settings.language.label`, …).
  Stringhe con parametri come funzioni tipizzate, es.
  `tracksCount: (n) => n === 1 ? "1 track" : n + " tracks"`.
  Plurali e interpolazione sono TypeScript puro, nessun mini-DSL.
- `it.ts`: `const it: typeof en = …` — chiave mancante o extra = errore di
  compilazione.
- `I18nProvider` + hook `useT()` sul pattern del provider tema esistente.
- Fallback runtime: in caso di chiave assente (teoricamente impossibile a
  compile-time) si mostra l'inglese.
- Migrazione pagina per pagina (~51 file): sostituzione delle stringhe
  hardcoded con `t.xxx`. Attenzione al gotcha Next 16 sugli spazi JSX
  (vedi `frontend/CLAUDE.md`).

## 3. Backend — codici errore

- I ~82 `HTTPException` passano a `detail` strutturato:
  `{"code": "playlist_not_found", "params": {...}, "message": "<inglese>"}`.
  Il `message` inglese resta come fallback leggibile per debug/curl.
- `frontend/lib/api.ts` (oggi: `throw new Error(detail)`) viene aggiornato:
  se `detail` contiene un `code`, traduce dal dizionario `errors.*`;
  altrimenti mostra `message` o la stringa com'è. Questo permette una
  migrazione endpoint per endpoint senza rotture.
- `label_it` (in `scoring.py`, `serializers.py`, `transitions.py`): il campo
  `label` con codice (`technically_safe` | `creative_risk` | `good_reset`)
  esiste già; il frontend traduce dal codice. `label_it` viene deprecato e
  poi rimosso.

## 4. Output AI

- I prompt in `app/services/ai_agent.py` ("Scrivi SEMPRE in italiano")
  diventano parametrici: la lingua viene letta da `AppState` a ogni chiamata
  e iniettata nel prompt ("Scrivi sempre in italiano" / "Always write in
  English").
- Schemi Pydantic e Validation Engine invariati.

## 5. Testing

- Backend: i test sugli errori si aggiornano ad asserire sul `code` (più
  stabile delle stringhe). Test nuovi per GET/PUT della lingua.
- Frontend: la rete di sicurezza principale è il type-check (chiavi complete
  per costruzione); `npm run build` + `npm run lint` come gate. Verifica
  manuale col dev server sulle pagine principali in entrambe le lingue.

## 6. Fasi di lavoro

1. **Infrastruttura**: setting `language` (backend) + `I18nProvider`/`useT()`
   + selettore in Impostazioni.
2. **Frontend UI**: migrazione pagine a `t.*` in blocchi:
   shell/nav → library/tracks → playlists/discovery → set-builder/sets → resto.
3. **Backend**: codici errore + aggiornamento `lib/api.ts` + test.
4. **`label_it`**: traduzione da codice lato frontend, rimozione del campo.
5. **AI**: prompt parametrici sulla lingua.

Ogni fase è committabile e funzionante da sola: l'app resta in italiano finché
il toggle non esiste, poi migra progressivamente.

## Fuori scope

- Routing per locale (`/en`, `/it`), SEO, negotiation `Accept-Language`.
- Traduzione della documentazione di progetto (docs/ resta com'è).
- Lingue oltre IT/EN (la struttura le permette, ma non si predispone nulla
  di specifico).
