"""HTTP per il dialog nativo di scelta percorso. Nessuna logica di business qui."""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.http_errors import api_error
from app.services import native_picker

router = APIRouter(prefix="/api/picker", tags=["picker"])


class PickAvailabilityOut(BaseModel):
    available: bool


class PickIn(BaseModel):
    kind: Literal["folder", "file"]
    start: str | None = None
    prompt: str | None = None


class PickOut(BaseModel):
    path: str | None


@router.get("/availability", response_model=PickAvailabilityOut)
def availability():
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
