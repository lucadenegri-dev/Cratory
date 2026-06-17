"""Capacità del client LLM: quali modelli accettano output_config.effort + adaptive thinking.

Haiku 4.5 (modello economico) rifiuta `effort` con un 400: il client deve ometterlo.
"""

from app.integrations.llm import _supports_effort


def test_effort_supported_on_capable_models():
    assert _supports_effort("claude-opus-4-8")
    assert _supports_effort("claude-sonnet-4-6")
    assert _supports_effort("claude-fable-5")


def test_effort_not_supported_on_economy_models():
    # Haiku 4.5 e i modelli pre-4.6 rifiutano effort/adaptive -> niente effort
    assert not _supports_effort("claude-haiku-4-5")
    assert not _supports_effort("claude-haiku-4-5-20251001")
    assert not _supports_effort("claude-sonnet-4-5")
