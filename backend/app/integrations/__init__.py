"""Interfacce verso servizi esterni (Spotify, SoundCloud, enrichment musicale, LLM).

Nuovo paradigma: il flusso parte da una playlist streaming. Le integrazioni stanno
dietro interfacce astratte; le implementazioni concrete vivono nei moduli accanto.
Regole comuni: cache persistente delle risposte, gestione rate limit, errori espliciti.

Separazione fonti dati DJ:
- Spotify/SoundCloud: identita' traccia + metadata editoriali (titolo, artista, cover,
  durata, isrc, url). NON forniscono BPM/key affidabili per il mixing.
- Enrichment musicale (MusicBrainz, GetSongBPM/Tunebat, Cyanite/Soundcharts, Last.fm):
  BPM, key/camelot, genere, mood, energia, danceability, label, release.
- Rekordbox (storico opzionale): se presente, resta la fonte piu' affidabile per BPM/key/beatgrid.
"""

from abc import ABC, abstractmethod
from typing import Any


class SpotifyClient(ABC):
    """Metadata editoriali + import playlist. NON fornisce BPM/key per il mixing."""

    @abstractmethod
    def get_track_metadata(self, spotify_track_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def get_artist(self, spotify_artist_id: str) -> dict[str, Any]: ...

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


class SoundCloudClient(ABC):
    """Import playlist/liked SoundCloud. Implementazione concreta in fase successiva."""

    @abstractmethod
    def get_playlist_tracks(self, playlist_url_or_id: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_liked_tracks(self) -> list[dict[str, Any]]: ...


class MusicFeatureProvider(ABC):
    """Provider di feature musicali per l'enrichment esterno (BPM, key, mood, energia...).

    Il matching usa, in ordine di priorita': ISRC -> platform_track_id ->
    artist+title+duration -> fuzzy artist+title. L'implementazione ritorna un dict
    con i campi disponibili e una `confidence` (0-100), oppure None se nessun match.
    """

    name: str = "provider"

    @abstractmethod
    def lookup(
        self,
        *,
        title: str | None,
        artist: str | None,
        isrc: str | None = None,
        duration_seconds: int | None = None,
    ) -> dict[str, Any] | None: ...


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
        """[{artist, title}] tracce top per un tag/genere (discovery gap-driven per genere)."""


class DiscogsClient(ABC):
    """Storico opzionale: release, label, cataloghi etichette (espansione libreria)."""

    @abstractmethod
    def search_release(self, query: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_label_releases(self, label_id: str) -> list[dict[str, Any]]: ...


class MusicBrainzClient(ABC):
    """Identificazione aperta: artisti, release, ISRC, label."""

    @abstractmethod
    def search_artist(self, name: str) -> list[dict[str, Any]]: ...
