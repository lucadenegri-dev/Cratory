"""Classificazione AI del genere: anello di riserva della catena.

Entra SOLO quando i provider non hanno dato un genere. L'output e' marcato
genre_source="ai" dal chiamante: mai spacciato per dato fattuale (CLAUDE.md).
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.integrations.llm import LLMError, LLMNotConfigured, get_llm_client
from app.services.genre_norm import normalize_genre

logger = logging.getLogger(__name__)

_SYSTEM = (
    "Sei un archivista musicale per DJ. Dato artista, titolo ed eventuali "
    "etichetta/anno, indica il genere principale del brano in 1-3 parole "
    "(es. 'Tech House', 'Drum & Bass'). Se non conosci il brano con ragionevole "
    "certezza rispondi con genre=null: MAI tirare a indovinare."
)
_SCHEMA = {
    "type": "object",
    "properties": {"genre": {"type": ["string", "null"]}},
    "required": ["genre"],
    "additionalProperties": False,
}


def suggest_genre(track) -> str | None:
    """Genere suggerito dall'AI, normalizzato. None = niente risposta affidabile."""
    if not settings.ai_api_key or not (track.artist and track.title):
        return None
    payload = {"artist": track.artist, "title": track.title,
               "label": track.label, "year": track.year}
    try:
        out = get_llm_client().complete_json(_SYSTEM, payload, _SCHEMA)
    except (LLMNotConfigured, LLMError) as exc:
        logger.warning("AI genere non disponibile per '%s - %s': %s",
                       track.artist, track.title, exc)
        return None
    return normalize_genre(out.get("genre"))
