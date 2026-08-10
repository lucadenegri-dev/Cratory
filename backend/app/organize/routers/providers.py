"""Router PROVIDERS: stato di configurazione dei provider esterni per la pagina
Settings (elenco uniforme alle Impostazioni di Cratory). Read-only."""

from fastapi import APIRouter

from app.organize.core.config import settings
from app.organize.integrations import acoustid
from app.organize.schemas import ProviderInfo
from app.organize.services import ai_tags

router = APIRouter(prefix="/api", tags=["providers"])


@router.get("/providers", response_model=list[ProviderInfo])
def list_providers():
    discogs_token = bool(settings.discogs_token)
    acoustid_ok = acoustid.acoustid_configured() and acoustid.fpcalc_available()
    ai_ok = ai_tags.is_configured()
    return [
        ProviderInfo(
            key="musicbrainz", name="MusicBrainz", category="metadati testuali",
            description="Identità del brano + label, genere (via tag) e anno. "
                        "Nessuna chiave richiesta (~1 richiesta/secondo).",
            env_vars=["DJORG_MUSICBRAINZ_USER_AGENT"],
            docs_url="https://musicbrainz.org/doc/MusicBrainz_API",
            status="connected",
        ),
        ProviderInfo(
            key="discogs", name="Discogs", category="metadati testuali",
            description="Riempie label/genere/anno mancanti dopo MusicBrainz. "
                        "Funziona senza token; DJORG_DISCOGS_TOKEN alza il rate limit.",
            env_vars=["DJORG_DISCOGS_TOKEN"],
            docs_url="https://www.discogs.com/settings/developers",
            status="configured" if discogs_token else "connected",
        ),
        ProviderInfo(
            key="acoustid", name="AcoustID / Chromaprint", category="fingerprint",
            description="Identità acustica del file → MBID (match MusicBrainz esatto, "
                        "alta confidenza). Richiede la chiave AcoustID e il binario fpcalc.",
            env_vars=["DJORG_ACOUSTID_API_KEY", "FPCALC"],
            docs_url="https://acoustid.org/",
            status="configured" if acoustid_ok else "missing",
        ),
        ProviderInfo(
            key="anthropic", name="Anthropic — AI", category="AI",
            description="Claude Haiku per suggerire artista/titolo e generi quando i tag mancano.",
            env_vars=["ANTHROPIC_API_KEY"],
            docs_url="https://docs.anthropic.com/",
            status="configured" if ai_ok else "missing",
        ),
    ]
