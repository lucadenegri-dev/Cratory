"""Classificazione AI del genere: anello di riserva della catena.

Entra SOLO quando i provider non hanno dato un genere. L'output e' marcato
genre_source="ai" dal chiamante: mai spacciato per dato fattuale (CLAUDE.md).

Lavora in batch: una chiamata LLM ogni BATCH_SIZE tracce invece di un round-trip
per traccia. Un chunk fallito viene saltato (nessun dato inventato) e le sue
tracce restano fuori dal risultato: il chiamante puo' cosi' distinguere "il
modello non conosce il brano" (genre=None, cacheabile) da "chiamata fallita"
(assente, da ritentare).
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.integrations.llm import LLMError, LLMNotConfigured, get_llm_client
from app.services.genre_norm import normalize_genre

logger = logging.getLogger(__name__)

BATCH_SIZE = 20  # tracce per chiamata LLM: prompt compatto, risposta affidabile

_SYSTEM = (
    "Sei un archivista musicale per DJ. Ricevi una lista di brani (artista, "
    "titolo, eventuali etichetta/anno), ognuno con un index. Per ciascuno indica "
    "il genere principale in 1-3 parole (es. 'Tech House', 'Drum & Bass'). Se non "
    "conosci un brano con ragionevole certezza rispondi genre=null per quel brano: "
    "MAI tirare a indovinare."
)
_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "genre": {"type": ["string", "null"]},
                },
                "required": ["index", "genre"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def suggest_genres(tracks) -> dict[int, str | None]:
    """Genere AI per un batch di tracce, normalizzato. {track.id: genere | None}.

    None = il modello non conosce il brano (esito valido, cacheabile). Le tracce
    di un chunk fallito o senza artista/titolo non compaiono nel risultato.
    Dizionario vuoto se l'AI non e' configurata.
    """
    if not settings.ai_api_key:
        return {}
    valid = [t for t in tracks if t.artist and t.title]
    out: dict[int, str | None] = {}
    for start in range(0, len(valid), BATCH_SIZE):
        chunk = valid[start:start + BATCH_SIZE]
        payload = {"tracks": [
            {"index": i, "artist": t.artist, "title": t.title,
             "label": t.label, "year": t.year}
            for i, t in enumerate(chunk)
        ]}
        try:
            res = get_llm_client().complete_json(_SYSTEM, payload, _SCHEMA)
        except (LLMNotConfigured, LLMError) as exc:
            logger.warning("AI genere non disponibile per un chunk di %d tracce: %s",
                           len(chunk), exc)
            continue
        by_index = {
            it["index"]: it.get("genre")
            for it in res.get("items", [])
            if isinstance(it, dict) and isinstance(it.get("index"), int)
        }
        for i, t in enumerate(chunk):
            if i in by_index:
                out[t.id] = normalize_genre(by_index[i])
    return out
