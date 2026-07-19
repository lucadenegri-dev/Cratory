"""Interfacce verso servizi esterni (Spotify, enrichment musicale, LLM).

Nuovo paradigma: il flusso parte da una playlist streaming. Le integrazioni stanno
dietro interfacce astratte; le implementazioni concrete vivono nei moduli accanto.
Regole comuni: cache persistente delle risposte, gestione rate limit, errori espliciti.

Separazione fonti dati DJ:
- Spotify: identita' traccia + metadata editoriali (titolo, artista, cover,
  durata, isrc, url). NON fornisce BPM/key affidabili per il mixing.
- Discogs: crate digging per genere/etichetta (Discovery).
"""

from abc import ABC, abstractmethod
from typing import Any


class SpotifyClient(ABC):
    """Metadata editoriali + import playlist. NON fornisce BPM/key per il mixing."""

    @abstractmethod
    def get_track_metadata(self, spotify_track_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def list_user_playlists(self) -> list[dict[str, Any]]:
        """Playlist dell'utente autenticato (incluse collaborative accessibili)."""

    @abstractmethod
    def get_playlist_tracks(self, playlist_id: str) -> list[dict[str, Any]]:
        """Tracce di una playlist (paginazione gestita internamente)."""

    @abstractmethod
    def get_liked_tracks(self) -> list[dict[str, Any]]:
        """Liked tracks dell'utente, se disponibili via API."""

    @abstractmethod
    def create_playlist(self, name: str, track_ids: list[str]) -> str:
        """Crea una playlist e ritorna il suo URL."""


class LLMClient(ABC):
    """L'output dell'agente e' sempre JSON validato dal Validation Engine.

    `schema` e' un JSON Schema che vincola l'output del modello; l'implementazione
    deve restituire un dict conforme (poi rivalidato con Pydantic a valle).
    """

    @abstractmethod
    def complete_json(
        self, system_prompt: str, payload: dict[str, Any], schema: dict[str, Any]
    ) -> dict[str, Any]: ...
