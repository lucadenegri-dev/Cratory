"""Interfacce verso servizi esterni (Spotify, enrichment musicale, LLM).

Nuovo paradigma: il flusso parte da una playlist streaming. Le integrazioni stanno
dietro interfacce astratte; le implementazioni concrete vivono nei moduli accanto.
Regole comuni: cache persistente delle risposte, gestione rate limit, errori espliciti.

Separazione fonti dati DJ:
- Spotify: identita' traccia + metadata editoriali (titolo, artista, cover,
  durata, isrc, url). NON fornisce BPM/key affidabili per il mixing.
- Last.fm: similarita' (Discovery). Discogs: crate digging per genere/etichetta.
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


class SimilarityClient(ABC):
    """Scoperta di artisti/tracce simili (Discovery mode, Fase F).

    Fonte di SIMILARITA' (es. Last.fm): dato un seed restituisce candidati affini.
    NON fornisce BPM/key (arrivano dopo, dall'enrichment) ne' identita' di streaming
    (quella la risolve Spotify). I metodi ritornano liste di dict normalizzati.
    """

    name: str = "similarity"

    @abstractmethod
    def similar_artists(self, artist: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """[{name, match(0-1)}] di artisti simili."""

    @abstractmethod
    def similar_tracks(self, artist: str, title: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """[{artist, title, match(0-1)}] di tracce simili a una traccia seed."""

    @abstractmethod
    def artist_top_tracks(self, artist: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """[{artist, title}] tracce piu' note di un artista (per concretizzare un artista simile)."""

    @abstractmethod
    def top_tracks_by_tag(self, tag: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """[{artist, title}] tracce top per un tag/genere."""
