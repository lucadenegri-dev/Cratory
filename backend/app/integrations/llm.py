"""Client LLM concreto (MVP 3) basato sull'SDK ufficiale Anthropic.

L'AI Set Agent passa qui sistema + payload + JSON schema; il client vincola
l'output del modello con structured outputs (output_config.format) e ritorna
un dict gia' conforme allo schema (poi rivalidato con Pydantic dal servizio).
"""

import json
import logging
from typing import Any

from app.core.config import settings
from app.integrations import LLMClient

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-4-8"
MAX_TOKENS = 16000

# Modelli che NON supportano `output_config.effort` né l'adaptive thinking: lo
# rifiutano con un 400. Haiku 4.5 (e i Sonnet/Opus pre-4.6) rientrano qui. Per
# questi modelli passiamo solo il formato JSON, niente effort, thinking disabilitato.
_NO_EFFORT_TAGS = ("haiku", "sonnet-4-5", "sonnet-4-0", "opus-4-5", "opus-4-1", "opus-4-0")


def _supports_effort(model: str) -> bool:
    """True se il modello accetta output_config.effort + adaptive thinking (Opus 4.6+, Sonnet 4.6, Fable)."""
    m = model.lower()
    return not any(tag in m for tag in _NO_EFFORT_TAGS)


class LLMError(Exception):
    pass


class LLMNotConfigured(LLMError):
    pass


class AnthropicLLMClient(LLMClient):
    def __init__(self, model: str | None = None) -> None:
        if not settings.ai_api_key:
            raise LLMNotConfigured(
                "AI_API_KEY mancante in backend/.env: impostare la chiave API Anthropic "
                "per usare l'AI Set Agent."
            )
        try:
            import anthropic  # import lazy: il pacchetto serve solo con l'AI attiva
        except ImportError as exc:  # pragma: no cover
            raise LLMNotConfigured("Pacchetto 'anthropic' non installato (pip install anthropic).") from exc

        self._anthropic = anthropic
        # timeout esplicito: meglio un errore chiaro che un handler appeso
        self.client = anthropic.Anthropic(
            api_key=settings.ai_api_key, timeout=settings.ai_timeout_seconds
        )
        self.model = model or settings.ai_model or DEFAULT_MODEL
        self.effort = settings.ai_effort
        self.thinking = settings.ai_thinking

    def complete_json(
        self, system_prompt: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any]:
        user_content = json.dumps(payload, ensure_ascii=False)
        # output_config/thinking dipendono dalle capacità del modello: i modelli
        # economici (Haiku 4.5) rifiutano `effort` e l'adaptive thinking con un 400.
        output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
        if _supports_effort(self.model):
            output_config["effort"] = self.effort  # senza questo alcuni modelli usano effort alto (lento)
            thinking = {"type": "adaptive"} if self.thinking == "adaptive" else {"type": "disabled"}
        else:
            thinking = {"type": "disabled"}
        try:
            # streaming + get_final_message: robusto contro i timeout su output lunghi
            with self.client.messages.stream(
                model=self.model,
                max_tokens=MAX_TOKENS,
                thinking=thinking,
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
                output_config=output_config,
            ) as stream:
                message = stream.get_final_message()
        except self._anthropic.APIError as exc:
            raise LLMError(f"Errore API LLM: {exc}") from exc

        text = next((b.text for b in message.content if b.type == "text"), None)
        if not text:
            raise LLMError("Risposta LLM senza contenuto testuale")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Output LLM non e' JSON valido: {exc}") from exc


def get_llm_client(model: str | None = None) -> LLMClient:
    """Factory del client LLM. Solleva LLMNotConfigured se manca la chiave.

    `model` opzionale sovrascrive `AI_MODEL` (oggi nessun call-site lo usa).
    """
    return AnthropicLLMClient(model)


def llm_configured() -> bool:
    return bool(settings.ai_api_key)
