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


class LLMError(Exception):
    pass


class LLMNotConfigured(LLMError):
    pass


class AnthropicLLMClient(LLMClient):
    def __init__(self) -> None:
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
        self.client = anthropic.Anthropic(api_key=settings.ai_api_key)
        self.model = settings.ai_model or DEFAULT_MODEL

    def complete_json(
        self, system_prompt: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any]:
        user_content = json.dumps(payload, ensure_ascii=False)
        try:
            # streaming + get_final_message: robusto contro i timeout su output lunghi
            with self.client.messages.stream(
                model=self.model,
                max_tokens=MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=system_prompt,
                messages=[{"role": "user", "content": user_content}],
                output_config={"format": {"type": "json_schema", "schema": schema}},
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


def get_llm_client() -> LLMClient:
    """Factory del client LLM. Solleva LLMNotConfigured se manca la chiave."""
    return AnthropicLLMClient()


def llm_configured() -> bool:
    return bool(settings.ai_api_key)
