"""Repara gli `url` SoundCloud salvati per errore come stream CDN temporaneo
(media-streaming.soundcloud.cloud) invece della pagina pubblica soundcloud.com:
bug storico di `normalize_soundcloud_item` (priorita' url/webpage_url invertita).

- `_apply_fields` sovrascrive uno stream url gia' salvato quando il nuovo norm
  porta una pagina pubblica valida (repara un ri-sync), senza toccare un url
  gia' buono ne' altre piattaforme.
- la migrazione in `db.py` NULLa gli url ancora sporchi sui DB esistenti (lo
  stream non e' reversibile in una pagina: nessun link e' meglio di uno rotto).
"""
from sqlalchemy.orm import sessionmaker

from app.db import Base, _make_engine, ensure_schema
from app.models import Track
from app.services.playlist_import import NormalizedTrack, _apply_fields

_STREAM_URL = "https://playback.media-streaming.soundcloud.cloud/59BCuNpfI0"
_PAGE_URL = "https://soundcloud.com/digger/cool-track"


def _sc_norm(url):
    return NormalizedTrack(
        platform="soundcloud", platform_track_id="42", title="T", artist="A",
        album=None, duration_seconds=None, url=url, artwork_url=None, isrc=None,
        added_at=None,
    )


def test_apply_fields_ripara_stream_url_con_pagina_pubblica():
    t = Track(source_type="soundcloud", url=_STREAM_URL)
    _apply_fields(t, _sc_norm(_PAGE_URL))
    assert t.url == _PAGE_URL


def test_apply_fields_non_tocca_una_pagina_gia_buona():
    t = Track(source_type="soundcloud", url=_PAGE_URL)
    _apply_fields(t, _sc_norm("https://soundcloud.com/digger/cool-track-v2"))
    assert t.url == _PAGE_URL  # invariato: non sovrascrive enrichment/dati esistenti validi


def test_apply_fields_riempie_se_vuoto_come_prima():
    t = Track(source_type="soundcloud")
    _apply_fields(t, _sc_norm(_PAGE_URL))
    assert t.url == _PAGE_URL


def test_apply_fields_non_tocca_url_di_altre_piattaforme():
    """Il repair e' scoped a soundcloud: per altre piattaforme resta il
    comportamento originale (fill-if-empty, mai overwrite)."""
    t = Track(source_type="spotify", url="https://open.spotify.com/track/x")
    norm = NormalizedTrack(
        platform="spotify", platform_track_id="x", title="T", artist="A",
        album=None, duration_seconds=None, url="https://open.spotify.com/track/y",
        artwork_url=None, isrc=None, added_at=None,
    )
    _apply_fields(t, norm)
    assert t.url == "https://open.spotify.com/track/x"


def test_migrazione_nulla_url_stream_e_lascia_le_pagine(tmp_path):
    engine = _make_engine(f"sqlite:///{tmp_path / 'sc.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    session = Session()
    bad = Track(source_type="soundcloud", url=_STREAM_URL)
    good = Track(source_type="soundcloud", url=_PAGE_URL)
    session.add_all([bad, good])
    session.commit()
    bad_id, good_id = bad.id, good.id
    session.close()

    ensure_schema(engine)  # deve essere idempotente: si puo' rilanciare senza effetti collaterali
    ensure_schema(engine)

    session = Session()
    assert session.get(Track, bad_id).url is None
    assert session.get(Track, good_id).url == _PAGE_URL
    session.close()
