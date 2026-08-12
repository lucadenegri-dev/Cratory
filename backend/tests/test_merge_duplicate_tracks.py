"""Fusione di due Track che puntano allo stesso file su disco."""

import pytest
from sqlalchemy import select

from app.models import Playlist, Track, playlist_tracks
from app.tools.merge_duplicate_tracks import fondi, trova_duplicati_per_path


@pytest.fixture()
def coppia(db):
    """Due tracce sullo stesso local_path, in due playlist diverse."""
    a = Track(source_type="spotify", platform="spotify", spotify_id="abc", isrc="IT1234567890",
              artist="Robert Leiner", title="Aqua Viva", bpm=139.86, camelot_key="4A",
              bpm_source="rekordbox", has_local_file=True, local_path="/lib/aqua.flac")
    b = Track(source_type="manual", platform="manual",
              artist="Robert Leiner", title="Aqua Viva", bpm=139.86, camelot_key="4A",
              bpm_source="cratory", has_local_file=True, local_path="/lib/aqua.flac")
    p1 = Playlist(platform="spotify", name="Set")
    p2 = Playlist(platform="spotify", name="Discovery")
    db.add_all([a, b, p1, p2])
    db.commit()
    db.execute(playlist_tracks.insert().values(playlist_id=p1.id, track_id=a.id))
    db.execute(playlist_tracks.insert().values(playlist_id=p2.id, track_id=b.id, added_by="cratory"))
    db.commit()
    return a, b, p1, p2


def test_trova_duplicati_per_path(db, coppia):
    a, b, _, _ = coppia
    dupes = trova_duplicati_per_path(db)
    assert len(dupes) == 1
    path, ids = dupes[0]
    assert path == "/lib/aqua.flac"
    assert set(ids) == {a.id, b.id}


def test_fusione_sposta_le_playlist_e_cancella_lo_scarto(db, coppia):
    a, b, p1, p2 = coppia
    esito = fondi(db, tenere_id=a.id, scartare_id=b.id)
    db.commit()

    assert esito["playlist_spostate"] == 1
    assert db.get(Track, b.id) is None

    playlists = set(db.scalars(
        select(playlist_tracks.c.playlist_id).where(playlist_tracks.c.track_id == a.id)
    ))
    assert playlists == {p1.id, p2.id}


def test_fusione_non_duplica_una_membership_gia_presente(db, coppia):
    """Se entrambe stanno nella stessa playlist, la fusione non viola la PK composta."""
    a, b, p1, _ = coppia
    db.execute(playlist_tracks.insert().values(playlist_id=p1.id, track_id=b.id))
    db.commit()

    fondi(db, tenere_id=a.id, scartare_id=b.id)
    db.commit()

    righe = db.execute(
        select(playlist_tracks).where(playlist_tracks.c.track_id == a.id,
                                      playlist_tracks.c.playlist_id == p1.id)
    ).all()
    assert len(righe) == 1


def test_rifiuta_di_fondere_una_traccia_con_se_stessa(db, coppia):
    a, _, _, _ = coppia
    with pytest.raises(ValueError, match="con se stessa"):
        fondi(db, tenere_id=a.id, scartare_id=a.id)
