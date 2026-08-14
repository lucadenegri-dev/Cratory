# Pulsante "Sfoglia" con dialog nativo macOS (porting da Cratory)

Data: 2026-08-08 · Stato: approvata

## Obiettivo

I due campi a percorso assoluto di Sortory — il path della source in "Add root"
(pagina Sources) e la destinazione per-root `target_root` (pagina Settings) —
vanno digitati a mano. Il browser non può rivelare percorsi assoluti dal
proprio file picker, ma il backend gira sulla stessa macchina: un pulsante
"Sfoglia…" fa aprire al backend il dialog nativo del Finder e riporta il
percorso scelto nel campo.

È il porting della feature già consegnata e collaudata in Cratory
(`DJProject01/docs/superpowers/specs/2026-08-07-settings-folder-picker-design.md`),
incluso il fix emerso nella review finale di Cratory: lo script AppleScript
dichiara `with timeout of 300 seconds` (il default degli Apple Event è 120 s)
e il timeout del subprocess sta sopra come rete di sicurezza.

## Backend

- `backend/app/services/native_picker.py`: porting 1:1 del servizio di Cratory
  (versione post-fix): `picker_available()` (darwin + osascript nel PATH),
  `build_script(kind, start, prompt)` (`choose folder`/`choose file` in System
  Events attivato, `with timeout of 300 seconds`, `start` come `default
  location` solo se directory esistente, escape dei doppi apici),
  `pick_path(kind, start=None, prompt=None, *, runner=subprocess.run)` con
  lock di modulo (`PickerBusyError`), guardia piattaforma
  (`PickerUnavailableError`), annullo/timeout → `None`,
  `SUBPROCESS_TIMEOUT_SECONDS = TIMEOUT_SECONDS + 10`.
- Router nuovo `backend/app/routers/picker.py` (il `files.py` di Sortory fa i
  tag; convenzione one-file-per-resource): `GET /api/picker/availability` →
  `{"available": bool}`; `POST /api/picker/pick`
  `{"kind": "folder"|"file", "start": str|null, "prompt": str|null}` →
  `{"path": str|null}` (null = annullo/timeout); 409 via `api_error` con
  codici `picker_unavailable` e `picker_busy`; 422 su `kind` non valido.
  Registrato in `main.py` accanto agli altri router.
- In Sortory i due punti d'uso sono cartelle, ma il servizio e l'endpoint
  restano `folder|file` come in Cratory: il porting 1:1 (codice e test già
  collaudati) costa meno di una variante ridotta.

## Frontend

- `frontend/components/path-picker-button.tsx`: porting del componente
  (`PathPickerButton`, bottone interno `type="button"`, spinner mentre il
  dialog è aperto) e dell'hook `usePickerAvailability()` (fetch al mount,
  errore = false). Client API in `lib/api.ts` (file unico, stile del repo):
  `pickerAvailability()` e `pickPath(kind, start?, prompt?)` via
  `apiGet`/`apiSend("POST", …)`.
- Montaggio, sempre `kind="folder"`, visibile solo se il picker è disponibile:
  - **AddSource** (`components/add-source.tsx`): pulsante accanto all'input
    del path; il percorso scelto riempie l'input, l'aggiunta resta sul
    pulsante Add.
  - **Settings, riga destinazione per-root** (`app/settings/page.tsx`):
    pulsante accanto all'input `target_root`; il salvataggio resta sul
    pulsante Save; vuoto continua a significare "rename only" (il pick non
    salva mai da solo).
- i18n in entrambe le lingue: `common.browseButton` ("Browse…"/"Sfoglia…") e,
  nel blocco `errors`, `picker_unavailable` e `picker_busy` (stessi testi di
  Cratory). `Dictionary` è il tipo di `en.ts`: chiavi prima lì, poi speculari
  in `it.ts`.

## Test e verifica

- Backend (pytest, `subprocess` sempre mockato): porting dei test di Cratory —
  availability per piattaforma, strip dello slash finale (root "/" resta "/"),
  file non strippato, annullo, timeout, lock busy/release, `start` inesistente
  ignorato, escape del prompt, wrapper `with timeout of 300 seconds` pinnato,
  runner che riceve `SUBPROCESS_TIMEOUT_SECONDS`; router: availability,
  pick ok/annullo, 409×2, 422.
- Frontend: **nessun unit test e nessuna introduzione di vitest** (il repo non
  ha setup di test frontend; prassi attuale = lint + build). Verifica live:
  pulsanti presenti nelle due pagine, percorso che riempie il campo,
  `osacompile` sulle varianti generate.

## Fuori scope

- Windows/headless (gate di availability, come in Cratory).
- Il campo "folder" relativo del force lookup in Issues (è un nome, non un percorso).
- Introduzione di un framework di unit test frontend.
- Refactoring del client API o di add-source/settings oltre l'aggiunta del pulsante.
