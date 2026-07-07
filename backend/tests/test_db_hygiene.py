"""Pulizia una-tantum disk-first (services/db_hygiene.py):
- azzeramento residui legacy sui lead,
- riallineamento delle possedute al disco.
"""
from app.models import Track
from app.services.db_hygiene import purge_lead_residue, realign_owned_from_disk
from app.services.genre_norm import normalize_genre


def _lead(db, **kw):
    t = Track(source_type="spotify", has_local_file=False, **kw)
    db.add(t); db.commit()
    return t


def _owned(db, path, **kw):
    t = Track(source_type="local_files", has_local_file=True, local_path=str(path), **kw)
    db.add(t); db.commit()
    return t


def test_purge_lead_residue_azzera_i_campi_senza_writer(db):
    t = _lead(db, title="Song", artist="A", label="Warp",
              genre="Techno", bpm=128.0, camelot_key="8A", energy=90)
    counts = purge_lead_residue(db, apply=True)
    db.refresh(t)
    assert t.genre is None and t.bpm is None and t.camelot_key is None
    assert t.energy is None
    # identità e label (writer attuali) restano
    assert t.title == "Song" and t.artist == "A" and t.label == "Warp"
    assert counts == {"genre": 1, "bpm": 1, "camelot_key": 1, "energy": 1}


def test_purge_lead_residue_non_tocca_le_possedute(db, tmp_path):
    o = _owned(db, tmp_path / "f.mp3", genre="House", bpm=124.0, camelot_key="7A", energy=70)
    purge_lead_residue(db, apply=True)
    db.refresh(o)
    assert o.genre == "House" and o.bpm == 124.0 and o.camelot_key == "7A" and o.energy == 70


def test_purge_lead_residue_dry_run_non_scrive(db):
    t = _lead(db, title="Song", artist="A", genre="Techno", bpm=128.0)
    counts = purge_lead_residue(db, apply=False)
    db.refresh(t)
    assert t.genre == "Techno" and t.bpm == 128.0     # niente scrittura
    assert counts["genre"] == 1 and counts["bpm"] == 1


def test_realign_owned_sovrascrive_dal_disco(db, tmp_path, monkeypatch):
    from app.services import db_hygiene

    p = tmp_path / "x.mp3"
    p.write_bytes(b"x")
    o = _owned(db, p, title="Old", artist="OldA", album="OldAlb", genre="OldGenre",
               label="OldLabel", bpm=128.0, camelot_key="8A", album_art_url="http://cover")
    monkeypatch.setattr(db_hygiene, "read_tags", lambda _p: {
        "title": "New", "artist": "NewA", "album": "NewAlb", "year": 2020,
        "isrc": "I1", "duration_seconds": 200, "genre": "Techno", "label": "Warp",
    })
    realign_owned_from_disk(db, apply=True)
    db.refresh(o)
    assert o.title == "New" and o.artist == "NewA" and o.album == "NewAlb"
    assert o.genre == normalize_genre("Techno") and o.label == "Warp"
    assert o.year == 2020 and o.isrc == "I1" and o.duration_seconds == 200
    # Rekordbox + cover intatti
    assert o.bpm == 128.0 and o.camelot_key == "8A" and o.album_art_url == "http://cover"
    assert o.energy is not None  # ricalcolato da bpm+genere


def test_realign_owned_svuota_campo_assente_nel_file(db, tmp_path, monkeypatch):
    from app.services import db_hygiene

    p = tmp_path / "x.mp3"; p.write_bytes(b"x")
    o = _owned(db, p, title="T", artist="A", album="HaAlbum")
    monkeypatch.setattr(db_hygiene, "read_tags", lambda _p: {
        "title": "T", "artist": "A", "album": None, "year": None,
        "isrc": None, "duration_seconds": None, "genre": None, "label": None,
    })
    realign_owned_from_disk(db, apply=True)
    db.refresh(o)
    assert o.album is None


def test_realign_owned_fallback_dal_nome_file(db, tmp_path, monkeypatch):
    from app.services import db_hygiene

    p = tmp_path / "Aphex Twin - Xtal.mp3"; p.write_bytes(b"x")
    o = _owned(db, p, title=None, artist=None)
    monkeypatch.setattr(db_hygiene, "read_tags", lambda _p: {
        "title": None, "artist": None, "album": None, "year": None,
        "isrc": None, "duration_seconds": None, "genre": None, "label": None,
    })
    realign_owned_from_disk(db, apply=True)
    db.refresh(o)
    assert o.artist == "Aphex Twin" and o.title == "Xtal"


def test_realign_owned_dry_run_non_scrive(db, tmp_path, monkeypatch):
    from app.services import db_hygiene

    p = tmp_path / "x.mp3"; p.write_bytes(b"x")
    o = _owned(db, p, title="Old", artist="OldA")
    monkeypatch.setattr(db_hygiene, "read_tags", lambda _p: {
        "title": "New", "artist": "NewA", "album": None, "year": None,
        "isrc": None, "duration_seconds": None, "genre": None, "label": None,
    })
    rep = realign_owned_from_disk(db, apply=False)
    db.refresh(o)
    assert o.title == "Old"                 # niente scrittura in dry-run
    assert rep["changed_tracks"] == 1


def test_realign_owned_conta_file_mancante(db, tmp_path):
    _owned(db, tmp_path / "non-esiste.mp3", title="T", artist="A")
    rep = realign_owned_from_disk(db, apply=True)
    assert rep["missing_file"] == 1
