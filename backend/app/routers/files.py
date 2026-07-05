"""HTTP per la ricerca di file audio locali. Nessuna logica di business qui."""
from fastapi import APIRouter, Query
from pydantic import BaseModel

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
