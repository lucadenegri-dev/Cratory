"""Dove sta il codice, e dove l'app scrive. Sono due cose diverse.

`BACKEND_DIR` è la cartella del codice; `DATA_DIR` quella dei dati — database,
log, cache, binari scaricati, `.env`. Oggi coincidono, e senza
`CRATORY_DATA_DIR` continuano a coincidere: chi non sa di questo seam non deve
accorgersi che esiste. In un bundle `.app` firmato devono divergere, perché la
cartella del codice è di sola lettura e scriverci invaliderebbe la firma.

Stessa forma di `CRATORY_BIN_DIR` e `CRATORY_VERSION`, e stessa disciplina: il
backend non indovina mai di essere dentro un bundle, si limita a onorare una
variabile che il packager imposta al lancio.

Modulo senza dipendenze di proposito. `main.py` chiama `load_dotenv()` prima di
importare `app.core.config`, perché `FPCALC` viene letto da `os.environ` e non
da pydantic-settings: importare `config` a quel punto costruirebbe `Settings()`
troppo presto. Qui non c'è niente da importare, quindi nessun vincolo d'ordine.
"""
from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent

DATA_DIR_ENV = "CRATORY_DATA_DIR"


def risolvi_data_dir(raw: str | None) -> Path:
    """Il valore grezzo della variabile diventa la cartella dei dati.

    Assente o vuota = `BACKEND_DIR`, cioè il comportamento di sempre. La `~`
    viene espansa, come già fa `expand_user_paths` in `config.py`.

    Un percorso relativo solleva invece di essere risolto contro la cwd: i dati
    finirebbero in un posto che dipende da come è stato lanciato il processo —
    esattamente il difetto che i validator di `config.py` dichiarano di aver
    corretto. È una configurazione sbagliata che non deve poter passare
    inosservata, e a questo punto l'app non ha ancora fatto niente.
    """
    testo = (raw or "").strip()
    if not testo:
        return BACKEND_DIR
    cartella = Path(testo).expanduser()
    if not cartella.is_absolute():
        raise RuntimeError(
            f"{DATA_DIR_ENV}={testo!r} è un percorso relativo. Serve un "
            "percorso assoluto: altrimenti i dati finiscono in una cartella "
            "che dipende dalla directory di lavoro del processo."
        )
    return cartella


DATA_DIR = risolvi_data_dir(os.environ.get(DATA_DIR_ENV))


def verifica_scrivibile(cartella: Path) -> None:
    """Solleva con un messaggio leggibile se non ci si può scrivere.

    Va chiamata all'avvio, prima di qualunque scrittura. In un'app
    impacchettata l'utente non ha un terminale da cui leggere uno stack trace:
    un `PermissionError` grezzo sepolto in un log che non sa di avere è
    indistinguibile da un'app che non parte e basta.

    È l'unico punto di questo modulo autorizzato a toccare il filesystem.
    """
    try:
        cartella.mkdir(parents=True, exist_ok=True)
        sonda = cartella / ".cratory-prova-scrittura"
        sonda.write_text("")
        sonda.unlink()
    except OSError as exc:
        raise RuntimeError(
            f"La cartella dei dati non è scrivibile: {cartella} ({exc}). "
            f"Impostare {DATA_DIR_ENV} su una cartella scrivibile."
        ) from exc
