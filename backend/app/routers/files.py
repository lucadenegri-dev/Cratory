"""HTTP per file locali: ricerca e dialog nativo di scelta percorso.
Nessuna logica di business qui."""
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.core.http_errors import api_error
from app.services import native_picker
from app.services.file_search import search_audio_files

router = APIRouter(prefix="/api/files", tags=["files"])


class LocalFileOut(BaseModel):
    path: str
    name: str
    format: str | None = None
    size: int | None = None
    source: str


@router.get("/search", response_model=list[LocalFileOut])
def search_files(q: str = Query(default="")):
    """Cerca file audio per nome in LIBRARY_ROOT e nella cartella download slskd."""
    return [LocalFileOut(**h) for h in search_audio_files(q)]


class PickAvailabilityOut(BaseModel):
    available: bool


class PickIn(BaseModel):
    kind: Literal["folder", "file"]
    start: str | None = None
    prompt: str | None = None


class PickOut(BaseModel):
    path: str | None


@router.get("/pick/availability", response_model=PickAvailabilityOut)
def pick_availability():
    """Il dialog nativo esiste solo su macOS con osascript nel PATH."""
    return PickAvailabilityOut(available=native_picker.picker_available())


@router.post("/pick", response_model=PickOut)
def pick(body: PickIn):
    """Apre il dialog nativo sulla macchina del backend; path null = annullato."""
    try:
        return PickOut(path=native_picker.pick_path(body.kind, body.start, body.prompt))
    except native_picker.PickerUnavailableError:
        raise api_error(409, "picker_unavailable",
                        "Native picker requires macOS with osascript")
    except native_picker.PickerBusyError:
        raise api_error(409, "picker_busy", "A picker dialog is already open")
