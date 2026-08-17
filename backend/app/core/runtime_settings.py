"""Config effettiva a runtime: override utente (da `AppState`, prefisso `cfg.`)
sopra i default di `.env` (`settings`).

Perché una cache in memoria e non una lettura dal DB a ogni accesso: molti
call-site che leggono questi valori (client slskd, job di indicizzazione/download,
`file_search`) non hanno una `Session` a portata. La cache si carica una volta
all'avvio (`load`, dopo `ensure_schema`) e le scritture (`apply`/`clear`)
aggiornano DB e cache insieme, così l'update dalla UI ha effetto senza riavvio.
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.app_state import delete_state, get_states_by_prefix, set_state

_PREFIX = "cfg."

# Campi path: l'override va espanso (~) come fa `config.expand_user_paths` per i .env.
_PATH_KEYS = frozenset({"library_root", "archive_root", "slskd_download_dir",
                        "slskd_config_path"})

# Campi editabili con default in `.env` (settings.X). `share_library` è escluso:
# è un flag solo-DB, senza controparte env.
ENV_BACKED_KEYS = ("library_root", "archive_root", "slskd_download_dir",
                   "slskd_url", "slskd_config_path", "ai_model")

# Credenziali: stessa semantica (override DB > default .env), ma il valore non
# esce mai dal backend — il router le espone solo mascherate.
SECRET_KEYS = ("spotify_client_id", "spotify_client_secret", "ai_api_key",
               "discogs_token", "acoustid_api_key", "slskd_api_key")

_overrides: dict[str, str] = {}


def load(db: Session) -> None:
    """Popola la cache dagli override persistiti. Va chiamato all'avvio, dopo
    `ensure_schema`, prima di servire richieste."""
    global _overrides
    _overrides = dict(get_states_by_prefix(db, _PREFIX))


def _resolved(key: str) -> str:
    """Valore effettivo di un campo env-backed: override (cache) se non vuoto,
    altrimenti il default `.env`. I path vengono espansi (idempotente sugli
    assoluti già espansi da `settings`)."""
    value = _overrides.get(key) or getattr(settings, key, "")
    if value and key in _PATH_KEYS:
        return str(Path(value).expanduser())
    return value


def library_root() -> str:
    return _resolved("library_root")


def archive_root() -> str:
    return _resolved("archive_root")


def slskd_download_dir() -> str:
    return _resolved("slskd_download_dir")


def slskd_url() -> str:
    return _resolved("slskd_url")


def slskd_config_path() -> str:
    return _resolved("slskd_config_path")


def ai_model() -> str:
    return _resolved("ai_model")


def spotify_client_id() -> str:
    return _resolved("spotify_client_id")


def spotify_client_secret() -> str:
    return _resolved("spotify_client_secret")


def ai_api_key() -> str:
    return _resolved("ai_api_key")


def discogs_token() -> str:
    return _resolved("discogs_token")


def acoustid_api_key() -> str:
    return _resolved("acoustid_api_key")


def slskd_api_key() -> str:
    return _resolved("slskd_api_key")


def secret(key: str) -> str:
    """Valore effettivo di una credenziale. `KeyError` fuori da `SECRET_KEYS`:
    un typo non deve poter leggere in silenzio un campo qualsiasi di Settings."""
    if key not in SECRET_KEYS:
        raise KeyError(key)
    return _resolved(key)


def share_library() -> bool:
    """Flag "Condividi libreria" (solo DB, default False)."""
    return _overrides.get("share_library") == "1"


DOWNLOAD_SLOTS_DEFAULT = 3
DOWNLOAD_SLOTS_MIN = 1
DOWNLOAD_SLOTS_MAX = 10


def download_slots() -> int:
    """Quanti download in parallelo (solo DB, default 3).

    Letto a ogni riempimento del pool, non all'avvio: cambiarlo ha effetto
    senza riavviare. Un valore illeggibile o fuori scala non deve poter
    bloccare la coda, quindi si riporta nei limiti invece di sollevare.
    """
    raw = _overrides.get("download_slots")
    try:
        value = int(raw) if raw else DOWNLOAD_SLOTS_DEFAULT
    except ValueError:
        return DOWNLOAD_SLOTS_DEFAULT
    return max(DOWNLOAD_SLOTS_MIN, min(value, DOWNLOAD_SLOTS_MAX))


def source(key: str) -> str:
    """`'db'` se c'è un override non vuoto in cache, altrimenti `'env'`."""
    return "db" if _overrides.get(key) else "env"


def apply(db: Session, key: str, value: str) -> None:
    """Imposta un override (persiste in `AppState` + aggiorna cache). Valore vuoto
    = azzera l'override (torna al default `.env`)."""
    if value:
        set_state(db, _PREFIX + key, value)
        _overrides[key] = value
    else:
        clear(db, key)


def clear(db: Session, key: str) -> None:
    """Rimuove l'override (torna al default `.env`)."""
    delete_state(db, _PREFIX + key)
    _overrides.pop(key, None)
