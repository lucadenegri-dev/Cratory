"""Pulizia una-tantum disk-first (services/db_hygiene.py):
- azzeramento residui legacy sui lead,
- riallineamento delle possedute al disco,
- allineamento retroattivo di Track.genre al genere del primary file.
"""
from app.models import Track
from app.organize.models import AudioFile, ScanRoot
from app.services.db_hygiene import (
    align_owned_genre_from_file,
    dedupe_by_audio_hash,
    purge_lead_residue,
    realign_owned_from_disk,
)
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


def _owned_with_primary_file(db, *, track_genre=None, file_genre=None, **track_kw):
    """Traccia posseduta con un primary file agganciato: fabbrica minima per i
    test di `align_owned_genre_from_file`, che legge il genere dal file gia'
    indicizzato (AudioFile), non dal disco."""
    root = ScanRoot(path="/tmp/lib")
    db.add(root); db.flush()
    t = Track(source_type="local_files", has_local_file=True, genre=track_genre, **track_kw)
    db.add(t); db.flush()
    f = AudioFile(root_id=root.id, track_id=t.id, path=f"/tmp/lib/{t.id}.mp3",
                  ext="mp3", size_bytes=1, hash_method="stream", status="present",
                  location="library", genre=file_genre)
    db.add(f); db.flush()
    t.primary_file_id = f.id
    db.commit()
    return t


def test_align_owned_genre_allinea_divergente(db):
    t = _owned_with_primary_file(db, track_genre="Electronic", file_genre="Progressive House")
    rep = align_owned_genre_from_file(db, apply=True)
    db.refresh(t)
    assert t.genre == "Progressive House"
    assert rep["changed_tracks"] == 1
    assert rep["sample"] == [{"id": t.id, "genre_before": "Electronic", "genre_after": "Progressive House"}]


def test_align_owned_genre_file_vuoto_non_tocca(db):
    t = _owned_with_primary_file(db, track_genre="Electronic", file_genre=None)
    rep = align_owned_genre_from_file(db, apply=True)
    db.refresh(t)
    assert t.genre == "Electronic"
    assert rep["changed_tracks"] == 0


def test_align_owned_genre_lead_senza_file_non_tocca(db):
    t = _lead(db, genre="Techno")
    rep = align_owned_genre_from_file(db, apply=True)
    db.refresh(t)
    assert t.genre == "Techno"
    assert rep["changed_tracks"] == 0


def test_align_owned_genre_dry_run_non_scrive(db):
    t = _owned_with_primary_file(db, track_genre="Electronic", file_genre="Progressive House")
    rep = align_owned_genre_from_file(db, apply=False)
    db.refresh(t)                                       # rilettura dal DB: niente scrittura
    assert t.genre == "Electronic"
    assert rep["changed_tracks"] == 1
    assert rep["sample"][0]["genre_after"] == "Progressive House"


def test_align_owned_genre_ricalcola_energia(db):
    t = _owned_with_primary_file(db, track_genre="Electronic", file_genre="Techno", bpm=128.0)
    before_energy = t.energy
    align_owned_genre_from_file(db, apply=True)
    db.refresh(t)
    assert t.genre == "Techno"
    assert t.energy != before_energy
    assert t.energy_source == "estimated"


def test_align_owned_genre_non_tocca_title_artist(db):
    # invariante di perimetro: solo genre, mai identita' (title/artist restano
    # quelli streaming anche quando il file ha valori diversi).
    t = _owned_with_primary_file(db, track_genre="Electronic", file_genre="Techno",
                                  title="Streaming Title", artist="Streaming Artist")
    f = db.get(AudioFile, t.primary_file_id)
    f.artist, f.title = "File Artist", "File Title"
    db.commit()
    align_owned_genre_from_file(db, apply=True)
    db.refresh(t)
    assert t.title == "Streaming Title" and t.artist == "Streaming Artist"
    assert t.genre == "Techno"


def test_dedupe_by_audio_hash_fonde_stesso_file(db):
    # Stesso file (stesso audio_hash) in due righe: tiene l'identità Spotify, fonde l'altra.
    a = Track(source_type="spotify", spotify_id="s1", title="Song", artist="X",
              isrc="I1", audio_hash="H1", has_local_file=True)
    b = Track(source_type="local_files", title="Song (Original Mix)", artist="X",
              audio_hash="H1", bpm=128.0, has_local_file=True)
    c = Track(source_type="spotify", title="Other", artist="Y", audio_hash="H2", has_local_file=True)
    db.add_all([a, b, c]); db.commit()
    bid = b.id

    n = dedupe_by_audio_hash(db, apply=True)

    assert n == 1
    assert db.query(Track).count() == 2      # c intatta
    db.refresh(a)
    assert a.bpm == 128.0                      # backfill dal duplicato
    assert a.spotify_id == "s1" and a.isrc == "I1"  # tenuta l'identità Spotify
    assert db.get(Track, bid) is None


def test_dedupe_by_audio_hash_dry_run_non_scrive(db):
    a = Track(source_type="spotify", title="S", artist="X", audio_hash="H", has_local_file=True)
    b = Track(source_type="local_files", title="S", artist="X", audio_hash="H", has_local_file=True)
    db.add_all([a, b]); db.commit()
    n = dedupe_by_audio_hash(db, apply=False)
    assert n == 1 and db.query(Track).count() == 2  # solo conteggio, nessuna fusione
