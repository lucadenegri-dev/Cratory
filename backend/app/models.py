"""Modelli SQLAlchemy.

Il punto di partenza e' una playlist Spotify. BPM/tonalita'/genere/mood/energia
vengono ricavati dal livello di enrichment esterno (services/enrichment +
services/feature_enrichment + integrations/).
"""

from datetime import date, datetime, timezone

from sqlalchemy import JSON, Column, Date, DateTime, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Associazione M2M brano<->playlist. `added_at` e' per-playlist (quando il brano e'
# stato aggiunto a QUELLA playlist). PK composta: una membership per coppia.
playlist_tracks = Table(
    "playlist_tracks",
    Base.metadata,
    Column("playlist_id", ForeignKey("playlists.id"), primary_key=True, index=True),
    Column("track_id", ForeignKey("tracks.id"), primary_key=True, index=True),
    Column("added_at", DateTime, nullable=True),
)


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    spotify_id: Mapped[str | None] = mapped_column(String, index=True)
    soundcloud_id: Mapped[str | None] = mapped_column(String, index=True)
    # Sorgente/piattaforma: spotify | soundcloud | manual
    source_type: Mapped[str] = mapped_column(String, index=True)
    # Identita' streaming generica (import da playlist) + matching enrichment
    platform: Mapped[str | None] = mapped_column(String, index=True)  # spotify | soundcloud
    platform_track_id: Mapped[str | None] = mapped_column(String, index=True)
    isrc: Mapped[str | None] = mapped_column(String, index=True)
    url: Mapped[str | None] = mapped_column(Text)
    added_at: Mapped[datetime | None] = mapped_column(DateTime)  # primo import in libreria; l'added_at per-playlist sta su playlist_tracks
    playlist_id: Mapped[int | None] = mapped_column(ForeignKey("playlists.id"), index=True)
    playlist_name: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    artist: Mapped[str | None] = mapped_column(String, index=True)
    album: Mapped[str | None] = mapped_column(String)
    album_id: Mapped[str | None] = mapped_column(String, index=True)  # id album Spotify (per backfill label)
    genre: Mapped[str | None] = mapped_column(String, index=True)  # genre_primary
    genre_secondary: Mapped[str | None] = mapped_column(String)
    year: Mapped[int | None] = mapped_column(Integer)
    release_date: Mapped[date | None] = mapped_column(Date)
    label: Mapped[str | None] = mapped_column(String)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    bpm: Mapped[float | None] = mapped_column(Float, index=True)
    camelot_key: Mapped[str | None] = mapped_column(String, index=True)  # tonalita' Camelot, es. "7A"
    # Feature musicali da enrichment esterno (0-100, mai inventate dall'AI)
    mood: Mapped[str | None] = mapped_column(String)
    energy: Mapped[int | None] = mapped_column(Integer)
    danceability: Mapped[int | None] = mapped_column(Integer)
    vocalness: Mapped[int | None] = mapped_column(Integer)
    # Stato traccia: imported | enriched | ready_for_set | missing_features | low_confidence
    status: Mapped[str] = mapped_column(String, default="imported", index=True)
    # Enrichment — cover, fonte e confidenza del match
    album_art_url: Mapped[str | None] = mapped_column(Text)  # artwork_url
    enrichment_source: Mapped[str | None] = mapped_column(String)  # musicbrainz|getsongbpm|lastfm
    enrichment_confidence: Mapped[int | None] = mapped_column(Integer)  # 0-100
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    playlists: Mapped[list["Playlist"]] = relationship(
        secondary="playlist_tracks", back_populates="tracks", viewonly=True,
    )


class SpotifyToken(Base):
    """Token OAuth Spotify. kind='user' (playlist) o 'client' (solo metadata)."""

    __tablename__ = "spotify_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String, unique=True)  # user | client
    access_token: Mapped[str] = mapped_column(Text)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    scope: Mapped[str | None] = mapped_column(Text)


class Playlist(Base):
    """Playlist importata da uno streaming (Spotify/SoundCloud). Punto di partenza del nuovo flusso."""

    __tablename__ = "playlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String, index=True)  # spotify | soundcloud
    platform_playlist_id: Mapped[str | None] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    owner: Mapped[str | None] = mapped_column(String)
    url: Mapped[str | None] = mapped_column(Text)
    artwork_url: Mapped[str | None] = mapped_column(Text)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String, default="playlist")  # playlist | liked
    imported_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    tracks: Mapped[list["Track"]] = relationship(
        secondary="playlist_tracks", back_populates="playlists", viewonly=True,
    )


class EnrichmentCache(Base):
    """Cache delle risposte dei provider feature (GetSongBPM, MusicBrainz...).
    Evita lookup ripetuti per la stessa traccia. result_json=None = not found (anch'esso cachato).
    """

    __tablename__ = "enrichment_cache"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String, index=True)
    lookup_key: Mapped[str] = mapped_column(String, index=True)
    result_json: Mapped[dict | None] = mapped_column(JSON)
    cached_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Setlist(Base):
    __tablename__ = "setlists"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    target_duration_minutes: Mapped[int | None] = mapped_column(Integer)
    start_bpm: Mapped[float | None] = mapped_column(Float)
    end_bpm: Mapped[float | None] = mapped_column(Float)
    strategy: Mapped[str | None] = mapped_column(String)
    prompt: Mapped[str | None] = mapped_column(Text)
    global_explanation: Mapped[str | None] = mapped_column(Text)
    generated_by: Mapped[str] = mapped_column(String, default="algorithmic")  # algorithmic | ai
    validation: Mapped[dict] = mapped_column(JSON, default=dict)  # warnings/auto-fix del Validation Engine
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    tracks: Mapped[list["SetlistTrack"]] = relationship(
        back_populates="setlist", cascade="all, delete-orphan", order_by="SetlistTrack.position"
    )


class SetlistTrack(Base):
    __tablename__ = "setlist_tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    setlist_id: Mapped[int] = mapped_column(ForeignKey("setlists.id"), index=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    # Ruolo della traccia nell'arco del set: intro|warmup|groove|transition|peak|release|closing
    role: Mapped[str | None] = mapped_column(String)
    transition_score: Mapped[float | None] = mapped_column(Float)
    transition_reason: Mapped[str | None] = mapped_column(Text)
    transition_note: Mapped[str | None] = mapped_column(Text)  # nota di transizione (AI o tecnica)
    ai_reason: Mapped[str | None] = mapped_column(Text)
    risk_level: Mapped[str | None] = mapped_column(String)  # low | medium | high
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    setlist: Mapped[Setlist] = relationship(back_populates="tracks")
    track: Mapped[Track] = relationship()


class DjSet(Base):
    """Un set/mix di un DJ identificato via Shazam (fingerprinting audio).

    Tenuto SEPARATO dalla libreria: le tracce identificate (DjSetTrack) NON sono
    `Track` e non entrano in libreria. Servono come corpus per i suggerimenti per
    co-occorrenza. `source_url` e' la chiave naturale per il caching (no re-analisi).
    """

    __tablename__ = "dj_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_url: Mapped[str] = mapped_column(Text, index=True)
    platform: Mapped[str | None] = mapped_column(String)  # soundcloud | mixcloud | youtube | ...
    title: Mapped[str | None] = mapped_column(String)
    dj_name: Mapped[str | None] = mapped_column(String, index=True)
    artwork_url: Mapped[str | None] = mapped_column(Text)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    # pending | identifying | done | error
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    identified_count: Mapped[int] = mapped_column(Integer, default=0)
    segments_total: Mapped[int | None] = mapped_column(Integer)  # quanti segmenti analizzati
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime)

    tracks: Mapped[list["DjSetTrack"]] = relationship(
        back_populates="dj_set", cascade="all, delete-orphan", order_by="DjSetTrack.position"
    )


class DjSetTrack(Base):
    """Traccia identificata dentro un DjSet. NON e' una traccia di libreria.

    Identita' debole (Shazam): artista+titolo, ISRC quando disponibile. Match verso
    la libreria/altri set per ISRC -> artist+title normalizzati.
    """

    __tablename__ = "dj_set_tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    dj_set_id: Mapped[int] = mapped_column(ForeignKey("dj_sets.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    start_offset_seconds: Mapped[int | None] = mapped_column(Integer)
    artist: Mapped[str | None] = mapped_column(String, index=True)
    title: Mapped[str | None] = mapped_column(String)
    isrc: Mapped[str | None] = mapped_column(String, index=True)
    apple_id: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[int | None] = mapped_column(Integer)  # 0-100 (euristica)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    dj_set: Mapped[DjSet] = relationship(back_populates="tracks")
