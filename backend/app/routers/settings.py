"""Impostazioni utente persistite in AppState (mono-utente, niente tabella dedicata).

Due gruppi:
- `/language`: preferenza lingua UI.
- `/config` + `/share-library`: override runtime dei path/URL di `.env`
  (`runtime_settings`) e flag "Condividi libreria" (edita `slskd.yml`).
"""
import os
import re
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import runtime_settings as rs
from app.core.config import settings
from app.core.http_errors import api_error
from app.db import get_db
from app.services import slskd_shares
from app.services.app_state import LANGUAGE_KEY, get_language, set_state

router = APIRouter(prefix="/api/settings", tags=["settings"])


class LanguageSetting(BaseModel):
    language: Literal["it", "en"]


@router.get("/language", response_model=LanguageSetting)
def read_language(db: Session = Depends(get_db)):
    return LanguageSetting(language=get_language(db))


@router.put("/language", response_model=LanguageSetting)
def write_language(req: LanguageSetting, db: Session = Depends(get_db)):
    set_state(db, LANGUAGE_KEY, req.language)
    return req


# --- Config editabile (path/URL) + flag condivisione libreria -----------------

# Directory il cui override deve puntare a una cartella esistente (vuoto = feature
# disattiva, come il default `.env`).
_DIR_KEYS = ("library_root", "archive_root", "slskd_download_dir")
# Tutti i campi in chiaro editabili: la sorgente è `runtime_settings`, non una
# seconda lista da tenere allineata a mano.
_FIELD_KEYS = rs.ENV_BACKED_KEYS


class FieldState(BaseModel):
    value: str
    source: Literal["env", "db"]
    valid: bool
    detail: str | None = None


class SecretState(BaseModel):
    """Stato di una credenziale. Il valore non esce mai: solo presenza,
    provenienza e le ultime 4 cifre per riconoscerla."""
    configured: bool
    source: Literal["env", "db"]
    hint: str | None = None


class ConfigSettings(BaseModel):
    library_root: FieldState
    archive_root: FieldState
    slskd_download_dir: FieldState
    slskd_url: FieldState
    slskd_config_path: FieldState
    ai_model: FieldState
    secrets: dict[str, SecretState]
    spotify_redirect_uri: str
    share_library: bool
    download_slots: int
    warning: str | None = None


class ConfigPatch(BaseModel):
    # Ogni campo è opzionale: assente = invariato; stringa vuota = azzera l'override.
    library_root: str | None = None
    archive_root: str | None = None
    slskd_download_dir: str | None = None
    slskd_url: str | None = None
    slskd_config_path: str | None = None
    ai_model: str | None = None
    spotify_client_id: str | None = None
    spotify_client_secret: str | None = None
    ai_api_key: str | None = None
    discogs_token: str | None = None
    acoustid_api_key: str | None = None
    slskd_api_key: str | None = None


def _validate(key: str, value: str) -> tuple[bool, str | None]:
    """(valido, dettaglio) per un campo. Vuoto = valido (disattiva la feature).
    `slskd_download_dir` non scrivibile è una nota, non un errore: Cratory lo legge
    soltanto. `slskd_config_path` invece deve essere scrivibile per la share."""
    expanded = str(Path(value).expanduser()) if value else ""
    if key in _DIR_KEYS:
        if not value:
            return True, "Disattivato (vuoto)"
        p = Path(expanded)
        if not p.exists():
            return False, "Il percorso non esiste"
        if not p.is_dir():
            return False, "Non è una cartella"
        if key == "slskd_download_dir" and not os.access(p, os.W_OK):
            return True, "Nota: cartella non scrivibile"
        return True, None
    if key == "slskd_url":
        if not value:
            return True, "Disattivato (vuoto)"
        if not re.match(r"^https?://", value):
            return False, "URL non valido (serve http:// o https://)"
        return True, None
    if key == "slskd_config_path":
        if not value:
            return True, None
        p = Path(expanded)
        if not p.is_file():
            return False, "File di config non trovato"
        if not os.access(p, os.W_OK):
            return False, "File di config non scrivibile"
        return True, None
    return True, None


def _field_state(key: str) -> FieldState:
    value = getattr(rs, key)()
    valid, detail = _validate(key, value)
    return FieldState(value=value, source=rs.source(key), valid=valid, detail=detail)


def _secret_state(key: str) -> SecretState:
    value = rs.secret(key)
    if not value:
        return SecretState(configured=False, source=rs.source(key), hint=None)
    hint = f"••••{value[-4:]}" if len(value) >= 4 else "••••"
    return SecretState(configured=True, source=rs.source(key), hint=hint)


def _snapshot(warning: str | None = None) -> ConfigSettings:
    return ConfigSettings(
        **{k: _field_state(k) for k in _FIELD_KEYS},
        secrets={k: _secret_state(k) for k in rs.SECRET_KEYS},
        spotify_redirect_uri=settings.spotify_redirect_uri,
        share_library=rs.share_library(),
        download_slots=rs.download_slots(),
        warning=warning,
    )


@router.get("/config", response_model=ConfigSettings)
def read_config():
    return _snapshot()


@router.patch("/config", response_model=ConfigSettings)
def patch_config(req: ConfigPatch, db: Session = Depends(get_db)):
    # `strip`: una chiave incollata porta spesso spazi o un newline finale, che
    # renderebbero invalido l'header verso il provider con un errore opaco.
    updates = {k: (v or "").strip() for k, v in req.model_dump(exclude_unset=True).items()}
    # Valida TUTTO prima di persistere qualsiasi cosa (niente stato parziale).
    for key, value in updates.items():
        valid, detail = _validate(key, value)
        if not valid:
            raise api_error(422, "invalid_setting",
                            f"{key}: {detail}", field=key, detail=detail)

    old_library = rs.library_root()
    for key, value in updates.items():
        rs.apply(db, key, value)

    # Se la share è attiva e la libreria è cambiata, ri-applicala (togli la vecchia,
    # metti la nuova). Best-effort: un problema col config non deve rompere il PATCH.
    warning = None
    new_library = rs.library_root()
    if rs.share_library() and old_library != new_library:
        try:
            if old_library:
                cfg = Path(rs.slskd_config_path())
                if cfg.is_file():
                    slskd_shares.edit_shares_yaml(cfg, old_library, enabled=False)
            if new_library:
                slskd_shares.set_library_share(True)
            else:
                rs.apply(db, "share_library", "")  # niente da condividere → auto-off
        except slskd_shares.ShareError as exc:
            warning = f"Libreria aggiornata, ma la condivisione non è stata ri-applicata: {exc}"

    return _snapshot(warning)


class ShareLibrarySetting(BaseModel):
    enabled: bool


class ShareLibraryResult(BaseModel):
    share_library: bool
    applied_to_yaml: bool
    rescan: bool


@router.put("/share-library", response_model=ShareLibraryResult)
def set_share_library(req: ShareLibrarySetting, db: Session = Depends(get_db)):
    """Attiva/disattiva la condivisione della libreria su Soulseek (edita slskd.yml
    + rescan). Persiste il flag. `409` se manca una precondizione (config assente/
    non scrivibile, o attivazione senza `library_root`)."""
    try:
        result = slskd_shares.set_library_share(req.enabled)
    except slskd_shares.ShareError as exc:
        raise api_error(409, "share_precondition", str(exc)) from exc
    rs.apply(db, "share_library", "1" if req.enabled else "")
    return ShareLibraryResult(
        share_library=req.enabled,
        applied_to_yaml=result["applied_to_yaml"],
        rescan=result["rescan"],
    )


class DownloadSlotsSetting(BaseModel):
    slots: int


class DownloadSlotsResult(BaseModel):
    download_slots: int


@router.put("/download-slots", response_model=DownloadSlotsResult)
def put_download_slots(req: DownloadSlotsSetting, db: Session = Depends(get_db)):
    """Quanti download in parallelo. Fuori scala e' un errore esplicito qui
    (l'utente ha digitato un numero), mentre il getter si limita a riportare
    nei limiti un valore gia' persistito."""
    if not (rs.DOWNLOAD_SLOTS_MIN <= req.slots <= rs.DOWNLOAD_SLOTS_MAX):
        raise api_error(422, "invalid_setting",
                        f"slots deve stare fra {rs.DOWNLOAD_SLOTS_MIN} e {rs.DOWNLOAD_SLOTS_MAX}",
                        field="slots")
    rs.apply(db, "download_slots", str(req.slots))
    return DownloadSlotsResult(download_slots=rs.download_slots())
