# Settings: pulsante "Sfoglia" con dialog nativo macOS

Data: 2026-08-07 · Stato: approvata (esteso in pari data: anche la modale
"Collega file locale")

## Obiettivo

In Settings i campi percorso (`library_root`, `archive_root`,
`slskd_download_dir`, `slskd_config_path`) vanno digitati a mano; lo stesso
vale per il campo "percorso esatto" della modale "Collega file locale". Il
browser non può rivelare percorsi assoluti dal proprio file picker, ma il
backend gira sulla stessa macchina: un pulsante "Sfoglia…" fa aprire al
backend il dialog nativo del Finder e riporta il percorso scelto nel campo.

Scelta di approccio: dialog nativo via `osascript` (macOS-only) invece di un
folder picker in-app cross-platform — decisione esplicita dell'utente, meno
codice; estendibile dopo.

## Backend (`routers/files.py`)

- `GET /api/files/pick/availability` → `{"available": bool}`: vero solo se
  `sys.platform == "darwin"` e `osascript` è nel PATH. Su Windows o ambienti
  senza GUI il frontend non mostra il pulsante.
- `POST /api/files/pick` body `{"kind": "folder" | "file", "start": str | null}`
  → `{"path": str | null}`:
  - lancia `osascript` con `choose folder` / `choose file` (`POSIX path of …`),
    preceduto dall'attivazione del processo per portare il dialog in primo
    piano; `start`, se è una directory esistente, diventa `default location`.
  - Annullamento utente (exit code 1 / "User canceled") → `{"path": null}`.
  - Timeout subprocess di 300 s → processo terminato, trattato come annullo
    (`{"path": null}`): il worker non resta appeso.
  - Un lock di modulo impedisce dialog concorrenti: se occupato → 409.
  - Non-darwin / osascript assente → 409 con dettaglio esplicito.
- La logica osascript sta in `services/` (funzione pura testabile con
  `subprocess` monkeypatchato); il router resta HTTP-only.

## Frontend (Settings, `ConfigCard`)

- Al mount, fetch di `availability`; se `available`, accanto agli input dei
  campi percorso compare il pulsante "Sfoglia…": scelta cartella per
  `library_root`, `archive_root`, `slskd_download_dir`; scelta file per
  `slskd_config_path`. `slskd_url` resta senza pulsante (URL di rete).
- Click → `POST /api/files/pick` con `start` = valore corrente della bozza;
  in attesa il pulsante mostra lo spinner ed è disabilitato (come gli altri
  bottoni busy). `path` non nullo → aggiorna **la bozza** del campo; il
  salvataggio resta manuale col pulsante Salva (validazione backend invariata).
  `path` nullo (annullo) → nessun cambiamento. 409 → messaggio d'errore nel
  banner esistente della card.
- Nuove stringhe i18n in entrambe le lingue (etichetta pulsante, prompt del
  dialog se serve, errore "picker occupato/non disponibile").

## Frontend (modale "Collega file locale")

- Stesso pulsante "Sfoglia…" (scelta file) accanto all'input "percorso esatto"
  di `link-local-file-modal.tsx`, visibile solo se il picker è disponibile.
  Il file scelto riempie l'input; il collegamento resta manuale col pulsante
  Collega (validazione backend invariata). La disponibilità arriva da un hook
  condiviso con Settings (un solo punto che interroga `availability`).
- Attenzione: l'input sta dentro un `<form>` — il pulsante Sfoglia deve avere
  `type="button"` per non scatenare il submit del collegamento.

## Test

- Backend (`backend/tests`): availability su darwin/non-darwin (monkeypatch di
  `sys.platform`/`shutil.which`); pick con `subprocess.run` monkeypatchato per
  successo (path restituito e strippato), annullo, timeout; 409 su lock
  occupato e su piattaforma non supportata; `start` inesistente ignorato.
- Frontend (vitest): il pulsante compare solo se `available`; click riempie la
  bozza senza salvare; annullo non tocca la bozza; errore mostrato nel banner.
  Per la modale: Sfoglia presente solo se `available`, il file scelto riempie
  il percorso esatto senza far partire il collegamento (pinna il
  `type="button"`).

## Fuori scope

- Supporto Windows (dialog PowerShell/WinForms) e ambienti headless.
- Uso del picker fuori da Settings e dalla modale "Collega file locale".
- Folder picker in-app cross-platform (alternativa A, scartata).
- Auto-salvataggio del percorso scelto.
