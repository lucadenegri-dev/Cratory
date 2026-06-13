"""Interfacce verso servizi esterni (Spotify, Discogs, MusicBrainz, LLM).

In MVP 1 sono solo contratti: le implementazioni arrivano in MVP 2 (Spotify),
MVP 3 (LLM) e MVP 4 (Discogs/MusicBrainz). Regole comuni per le implementazioni:
cache persistente delle risposte, gestione rate limit, errori espliciti.
"""

from abc import ABC, abstractmethod
from typing import Any


class SpotifyClient(ABC):
    """MVP 2. Non deve MAI fornire BPM/key: quelli arrivano da Rekordbox."""

    @abstractmethod
    def get_track_metadata(self, spotify_track_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def get_artist(self, spotify_artist_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def create_playlist(self, name: str, track_ids: list[str]) -> str:
        """Crea una playlist e ritorna il suo URL."""


class LLMClient(ABC):
    """MVP 3. L'output dell'agente e' sempre JSON validato dal Validation Engine.

    `schema` e' un JSON Schema che vincola l'output del modello; l'implementazione
    deve restituire un dict conforme (poi rivalidato con Pydantic a valle).
    """

    @abstractmethod
    def complete_json(
        self, system_prompt: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any]: ...


class DiscogsClient(ABC):
    """MVP 4."""

    @abstractmethod
    def search_release(self, query: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_label_releases(self, label_id: str) -> list[dict[str, Any]]: ...


class MusicBrainzClient(ABC):
    """MVP 4 (fallback aperto)."""

    @abstractmethod
    def search_artist(self, name: str) -> list[dict[str, Any]]: ...
