"""Capacità del client LLM: quali modelli accettano output_config.effort + adaptive thinking.

Haiku 4.5 (modello economico) rifiuta `effort` con un 400: il client deve ometterlo.
"""

from app.integrations.llm import _sanitize_schema, _supports_effort


def test_effort_supported_on_capable_models():
    assert _supports_effort("claude-opus-4-8")
    assert _supports_effort("claude-sonnet-4-6")
    assert _supports_effort("claude-fable-5")


def test_effort_not_supported_on_economy_models():
    # Haiku 4.5 e i modelli pre-4.6 rifiutano effort/adaptive -> niente effort
    assert not _supports_effort("claude-haiku-4-5")
    assert not _supports_effort("claude-haiku-4-5-20251001")
    assert not _supports_effort("claude-sonnet-4-5")


def test_sanitize_schema_strips_unsupported_validation_keywords():
    # Gli structured outputs Anthropic rifiutano con un 400 le keyword di range/
    # lunghezza (minimum/maximum su integer, maxItems su array): vanno rimosse
    # prima dell'invio, i limiti restano garantiti dal post-processing dei servizi.
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "tags": {"type": "array", "items": {"type": "string"}, "maxItems": 3},
        },
        "required": ["score", "tags"],
    }
    clean = _sanitize_schema(schema)
    assert "minimum" not in clean["properties"]["score"]
    assert "maximum" not in clean["properties"]["score"]
    assert "maxItems" not in clean["properties"]["tags"]
    # la struttura sopravvive intatta
    assert clean["properties"]["score"]["type"] == "integer"
    assert clean["properties"]["tags"]["items"] == {"type": "string"}
    assert clean["required"] == ["score", "tags"]
    # non muta l'input originale
    assert schema["properties"]["score"]["minimum"] == 0


def test_sanitize_schema_preserves_enum_and_recurses_into_arrays():
    # enum/type/required sono strutturali e supportati: NON vanno toccati.
    # La ricorsione deve entrare anche negli item di array e nelle liste anyOf.
    schema = {
        "type": "object", "additionalProperties": False,
        "properties": {
            "strategy": {"type": ["string", "null"], "enum": ["smooth", None]},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"n": {"type": "integer", "minimum": 1}},
                    "maxItems": 5,
                },
            },
        },
        "required": ["strategy", "items"],
    }
    clean = _sanitize_schema(schema)
    assert clean["properties"]["strategy"]["enum"] == ["smooth", None]
    assert "maxItems" not in clean["properties"]["items"]
    assert "minimum" not in clean["properties"]["items"]["items"]["properties"]["n"]
