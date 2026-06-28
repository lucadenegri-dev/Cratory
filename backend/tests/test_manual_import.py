"""Test import manuale playlist (testo libero / CSV). Nessuna rete."""

from app.models import Playlist, Track
from app.services.manual_import import import_manual_playlist, parse_line


def test_parse_line_formats():
    assert parse_line("Daft Punk - Da Funk") == ("Daft Punk", "Da Funk")
    assert parse_line("Boards of Canada – Roygbiv") == ("Boards of Canada", "Roygbiv")  # en dash
    assert parse_line("Aphex Twin — Xtal") == ("Aphex Twin", "Xtal")                    # em dash
    assert parse_line("artist,title") == ("artist", "title")                             # CSV
    assert parse_line("Just A Title") == (None, "Just A Title")                          # solo titolo
    assert parse_line("   ") is None                                                     # riga vuota


def test_import_manual_playlist(db):
    text = "Daft Punk - Da Funk\nBonobo - Kerala\nDaft Punk - Da Funk\n\nOnly Title"
    report = import_manual_playlist(db, name="My Mix", text=text)
    assert report["created"] == 3   # Da Funk, Kerala, Only Title
    assert report["skipped"] == 1   # duplicato Da Funk nello stesso incolla
    assert report["total"] == 3

    pl = db.query(Playlist).filter_by(name="My Mix").one()
    assert pl.platform == "manual"
    assert pl.kind == "manual"
    assert pl.track_count == 3
    from app.repositories import tracks_for_playlist
    tracks = tracks_for_playlist(db, pl.id)
    assert {t.title for t in tracks} == {"Da Funk", "Kerala", "Only Title"}
    assert all(t.source_type == "manual" for t in tracks)


def test_manual_dedup_against_existing_library(db):
    import_manual_playlist(db, name="A", text="Daft Punk - Da Funk")
    report = import_manual_playlist(db, name="B", text="Daft Punk - Da Funk\nNew Artist - New Song")
    assert report["created"] == 1   # solo New Song e' nuova
    assert report["updated"] == 1   # Da Funk gia' in libreria: riattaccata
    assert db.query(Track).filter(Track.title == "Da Funk").count() == 1  # niente duplicati per nome


def test_import_manual_empty_text(db):
    report = import_manual_playlist(db, name="Vuota", text="\n\n   \n")
    assert report["total"] == 0
    assert report["created"] == 0
