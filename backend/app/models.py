"""Modelli SQLAlchemy.

Il punto di partenza e' una playlist Spotify. BPM/tonalita'/genere arrivano da
provider esterni o da correzione manuale; l'energia e' stimata in modo
deterministico (services/energy). Nessun motore di enrichment interno.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# Associazione M2M brano<->playlist. `added_at` e' per-playlist (quando il brano e'
# stato aggiunto a QUELLA playlist). PK composta: una membership per coppia.
# `added_by`: provenienza della membership — NULL = import dalla piattaforma,
# 'cratory' = aggiunta da una feature Cratory (es. Discovery). Il prune del sync
# non tocca mai le membership 'cratory' (il write-back Spotify puo' fallire).
playlist_tracks = Table(
    "playlist_tracks",
    Base.metadata,
    Column("playlist_id", ForeignKey("playlists.id"), primary_key=True, index=True),
    Column("track_id", ForeignKey("tracks.id"), primary_key=True, index=True),
    Column("added_at", DateTime, nullable=True),
    Column("added_by", String, nullable=True),
)


class Track(Base):
    __tablename__ = "tracks"

    id: Mapped[int] = mapped_column(primary_key=True)
    spotify_id: Mapped[str | None] = mapped_column(String, index=True)
    soundcloud_id: Mapped[str | None] = mapped_column(String, index=True)
    # Sorgente/piattaforma: spotify | soundcloud | manual
    source_type: Mapped[str] = mapped_column(String, index=True)
    # Identita' streaming generica (import da playlist)
    platform: Mapped[str | None] = mapped_column(String, index=True)  # spotify | soundcloud
    platform_track_id: Mapped[str | None] = mapped_column(String, index=True)
    isrc: Mapped[str | None] = mapped_column(String, index=True)
    url: Mapped[str | None] = mapped_column(Text)
    # Path assoluto del file per le tracce locali (source_type="local_files"). Riferimento
    # volatile (non si conserva l'audio): aggiornato a ogni ri-scansione se il file si sposta.
    local_path: Mapped[str | None] = mapped_column(Text)
    has_local_file: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", index=True)
    local_format: Mapped[str | None] = mapped_column(String)
    local_bitrate: Mapped[int | None] = mapped_column(Integer)
    # Stato del file all'ultimo aggancio (per la scansione incrementale:
    # path+mtime+size invariati => niente ri-hash).
    local_mtime: Mapped[float | None] = mapped_column(Float)
    local_size: Mapped[int | None] = mapped_column(Integer)
    # Scartata: il file e' finito nell'archivio (PASSED in DJPlayer). Esclusa da
    # wishlist/discovery/download; il possesso in Libreria la riabilita.
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0", index=True)
    # Ultimo esito del download Soulseek (needs_review | not_found | failed |
    # downloaded): alimenta la sezione "da sistemare", che deve sopravvivere
    # a job e riavvii (lo stato del job e' in memoria).
    last_download_outcome: Mapped[str | None] = mapped_column(String)
    last_download_reason: Mapped[str | None] = mapped_column(String)
    # Path del file dubbio nell'inbox slskd quando l'esito è needs_review-per-durata:
    # alimenta la revisione "Tieni comunque / Scarta". None se non c'è file da rivedere.
    last_download_path: Mapped[str | None] = mapped_column(Text)
    # Identità audio (SHA-256 dello stream decodificato, vedi integrations/local_files.audio_hash):
    # stabile a rinomina/retag. Calcolata al download (acquisition) e all'indicizzazione libreria.
    audio_hash: Mapped[str | None] = mapped_column(String, index=True)
    added_at: Mapped[datetime | None] = mapped_column(DateTime)  # primo import in libreria; l'added_at per-playlist sta su playlist_tracks
    # Legacy pre-M2M (playlist di provenienza sulla traccia): superate da playlist_tracks
    # e svuotate dal backfill. Non droppabili: FK baked-in su playlist_id -> DROP COLUMN
    # richiederebbe un rebuild di `tracks`, che il progetto evita per FK-safety.
    playlist_id: Mapped[int | None] = mapped_column(ForeignKey("playlists.id"), index=True)
    playlist_name: Mapped[str | None] = mapped_column(String)
    title: Mapped[str | None] = mapped_column(String)
    artist: Mapped[str | None] = mapped_column(String, index=True)
    album: Mapped[str | None] = mapped_column(String)
    genre: Mapped[str | None] = mapped_column(String, index=True)  # genre_primary
    year: Mapped[int | None] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    bpm: Mapped[float | None] = mapped_column(Float, index=True)
    camelot_key: Mapped[str | None] = mapped_column(String, index=True)  # tonalita' Camelot, es. "7A"
    # Energia (0-100). Da BPM/genere (proxy) oppure calcolata dai file audio (PR4).
    energy: Mapped[int | None] = mapped_column(Integer)
    # Feature audio grezza (0..1) e provenienza dell'energia: computed | estimated.
    energy_raw: Mapped[float | None] = mapped_column(Float)
    energy_source: Mapped[str | None] = mapped_column(String)
    # Provenienza di bpm/camelot_key: manual | rekordbox | cratory (null se il
    # valore e' null). Gerarchia: manual > rekordbox > cratory; l'import
    # Rekordbox sovrascrive di default solo i valori 'cratory'.
    bpm_source: Mapped[str | None] = mapped_column(String)
    key_source: Mapped[str | None] = mapped_column(String)
    # Analisi BPM/key in-app (Essentia). Il job scrive SOLO questi campi: i
    # canonici bpm/camelot_key cambiano solo via apply (vedi services/audio_analysis).
    analysis_bpm: Mapped[float | None] = mapped_column(Float)
    analysis_camelot: Mapped[str | None] = mapped_column(String)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime)
    analysis_error: Mapped[str | None] = mapped_column(String)
    # Stato traccia: imported | ready_for_set
    status: Mapped[str] = mapped_column(String, default="imported", index=True)
    album_art_url: Mapped[str | None] = mapped_column(Text)  # artwork_url (cover album)
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
    # Disk-first: True se il set e' nato con la garanzia "solo brani posseduti".
    # L'editor (replace/alternative) la fa rispettare leggendo questo flag.
    owned_only: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    validation: Mapped[dict] = mapped_column(JSON, default=dict)  # warnings/auto-fix del Validation Engine
    # Curatela AI (tappa 2): intento compilato ("come ti ho capito"), warning
    # delle chiamate AI. {} = set non curato.
    curation: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
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
    # Tag di mood assegnati dalla curatela AI alla generazione (None = non curato).
    mood_tags: Mapped[list | None] = mapped_column(JSON)
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
    # Playlist creata da "Importa come playlist"; azzerata quando quella playlist
    # viene cancellata, così la re-import torna possibile.
    imported_playlist_id: Mapped[int | None] = mapped_column(Integer, index=True)
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


class AppState(Base):
    """Chiave-valore minimale per stato applicativo persistente (es. last_index_at:
    lo stato del job di indicizzazione vive in memoria e si perde al riavvio)."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class ArchiveSeen(Base):
    """Firma (path, mtime, size) dei file d'archivio che non corrispondono ad alcuna
    traccia: senza una Track non li vedrebbe la passata incrementale e verrebbero
    ri-hashati (ffmpeg) a ogni indicizzazione. Qui li ricordiamo per saltarli."""

    __tablename__ = "archive_seen"

    path: Mapped[str] = mapped_column(String, primary_key=True)
    mtime: Mapped[float] = mapped_column(Float)
    size: Mapped[int] = mapped_column(Integer)
